from flask import Flask, request, jsonify
from flask_cors import CORS

from config import PORT, BOT_NAME, DEFAULT_REPLY, check_config
from services.router_service import route_message_for_ai, get_welcome_message
from services.gemini_service import ask_gemini
from services.zalo_service import send_zalo_text
from services.logger import write_log, log_error, debug_log
from services.session_manager import get_context, save_context, clear_context

app = Flask(__name__)
CORS(app)

processed_messages = set()
MAX_PROCESSED_MESSAGES = 5000


def remember_message(message_id):
    # Chức năng: Kiểm tra và ghi nhớ message_id đã xử lý.
    # Vai trò: Tránh BOT trả lời trùng khi Zalo gửi lại cùng một webhook.
    if not message_id:
        return False

    if message_id in processed_messages:
        return True

    processed_messages.add(message_id)

    if len(processed_messages) > MAX_PROCESSED_MESSAGES:
        processed_messages.clear()

    return False


def build_answer(user_id, question):
    # Chức năng: Xây dựng câu trả lời cuối cùng cho một tin nhắn người dân.
    # Vai trò: Điều phối Session → Router → Gemini → Log → Session trong BOT CAP.
    context = get_context(user_id)

    debug_log("INPUT", {
        "user_id": user_id,
        "question": question,
        "context_before": context,
    })

    routed = route_message_for_ai(
        question,
        context=context,
    )

    debug_log("ROUTER_RESULT", {
        "reply": routed.get("reply"),
        "source": routed.get("source"),
        "use_ai": routed.get("use_ai"),
        "context_after": routed.get("context"),
        "ai_context": routed.get("ai_context"),
    })

    answer = routed.get("reply") or DEFAULT_REPLY
    source = routed.get("source") or "DEFAULT"
    use_ai = bool(routed.get("use_ai", False))
    new_context = routed.get("context", context)
    ai_context = routed.get("ai_context", "")

    if use_ai:
        ai_answer = ask_gemini(question, context=ai_context)

        if ai_answer and ai_answer.strip() != DEFAULT_REPLY:
            answer = (
                ai_answer.strip()
                + "\n\n────────────────\n"
                + "🤖 Lưu ý: Nội dung trên do AI hỗ trợ trả lời. "
                + "Quý công dân có thể nhắn 'menu' để xem danh mục hỗ trợ chính thức từ Google Sheets."
            )
            source = "GEMINI_AI"
        else:
            answer = (
                "Xin lỗi, hiện tôi chưa có đủ dữ liệu để trả lời chính xác nội dung này.\n\n"
                "Quý công dân vui lòng nhập rõ hơn nội dung cần hỗ trợ, ví dụ:\n"
                "• Làm căn cước ở đâu\n"
                "• Đăng ký tạm trú cần giấy tờ gì\n"
                "• Số điện thoại Công an phường\n"
                "• menu"
            )
            source = "AI_FALLBACK"

    if source == "RESET":
        clear_context(user_id)
    elif source == "WELCOME":
        save_context(user_id, {})
    else:
        save_context(user_id, new_context or {})

    write_log(
        user_id=user_id,
        user_message=question,
        bot_reply=answer,
        source=source,
    )

    debug_log("FINAL_ANSWER", {
        "source": source,
        "answer": answer,
        "context_saved": new_context,
    })

    return answer, source


@app.route("/", methods=["GET"])
def home():
    # Chức năng: Trang kiểm tra nhanh dịch vụ.
    # Vai trò: Kiểm tra Render/App đang hoạt động.
    ok, missing = check_config()

    return jsonify({
        "status": "ok" if ok else "warning",
        "bot": BOT_NAME,
        "version": "BOT CAP V3.0",
        "message": "Bot đang hoạt động",
        "missing_config": missing,
    })


@app.route("/health", methods=["GET"])
def health():
    # Chức năng: Kiểm tra tình trạng cấu hình hệ thống.
    # Vai trò: Phục vụ Render Health Check và giám sát hệ thống.
    ok, missing = check_config()

    return jsonify({
        "status": "ok" if ok else "missing_config",
        "bot": BOT_NAME,
        "missing": missing,
    })


@app.route("/test-ai", methods=["GET", "POST"])
def test_ai():
    # Chức năng: Kiểm thử Router + AI trực tiếp.
    # Vai trò: Hỗ trợ kiểm thử trong quá trình phát triển BOT.
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()
        user_id = str(data.get("user_id", "test-web")).strip()
    else:
        question = str(request.args.get("q", "menu")).strip()
        user_id = str(request.args.get("user_id", "test-web")).strip()

    answer, source = build_answer(
        user_id=user_id,
        question=question,
    )

    return jsonify({
        "success": True,
        "question": question,
        "answer": answer,
        "source": source,
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    # Chức năng: API Chat nội bộ.
    # Vai trò: Cho phép Web/App gọi trực tiếp BOT mà không qua Zalo.
    data = request.get_json(silent=True) or {}

    user_id = str(data.get("user_id", "web")).strip()
    question = str(data.get("question", "")).strip()

    if not question:
        return jsonify({
            "success": False,
            "message": "Missing question",
        }), 400

    answer, source = build_answer(
        user_id=user_id,
        question=question,
    )

    return jsonify({
        "success": True,
        "answer": answer,
        "source": source,
    })

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Chức năng: Tiếp nhận webhook từ Zalo OA.
    # Vai trò: Nhận tin nhắn người dân, gọi BOT xử lý và gửi trả lời qua Zalo.
    if request.method == "GET":
        return jsonify({
            "status": "ok",
            "message": "Webhook OK",
            "bot": BOT_NAME,
        }), 200

    data = request.get_json(silent=True) or {}

    try:
        print("WEBHOOK DATA:", data)

        event_name = data.get("event_name", "")
        sender = data.get("sender", {}) or {}
        message_data = data.get("message", {}) or {}

        user_id = (
            sender.get("id", "")
            or data.get("user_id_by_app", "")
            or data.get("user_id", "")
        )

        if not user_id:
            return jsonify({
                "success": False,
                "message": "Missing user_id",
            }), 400

        if event_name != "user_send_text":
            send_zalo_text(
                user_id=user_id,
                message=get_welcome_message(),
            )
            return jsonify({
                "success": True,
                "message": "Non-text event handled",
            }), 200

        message_id = (
            message_data.get("msg_id")
            or message_data.get("message_id")
            or data.get("message_id")
            or ""
        )

        if remember_message(message_id):
            return jsonify({
                "success": True,
                "message": "Duplicate ignored",
            }), 200

        question = str(message_data.get("text", "") or "").strip()

        if not question:
            send_zalo_text(
                user_id=user_id,
                message=get_welcome_message(),
            )
            return jsonify({
                "success": True,
                "message": "Empty text handled",
            }), 200

        answer, source = build_answer(
            user_id=user_id,
            question=question,
        )

        send_zalo_text(
            user_id=user_id,
            message=answer,
        )

        return jsonify({
            "success": True,
            "source": source,
        }), 200

    except Exception as e:
        import traceback

        error_message = f"Lỗi xử lý webhook: {e}"
        print("[WEBHOOK ERROR]", error_message)
        print(traceback.format_exc())

        try:
            sender = data.get("sender", {}) or {}
            message_data = data.get("message", {}) or {}
            user_id = sender.get("id", "") or data.get("user_id_by_app", "")
            question = message_data.get("text", "")

            if user_id:
                send_zalo_text(
                    user_id=user_id,
                    message=DEFAULT_REPLY,
                )

            log_error(
                user_id=user_id,
                user_message=question,
                error_message=error_message,
            )

        except Exception as log_e:
            print("[WEBHOOK LOG ERROR]", log_e)

        return jsonify({
            "success": False,
            "message": str(e),
        }), 200


if __name__ == "__main__":
    # Chức năng: Khởi động Flask khi chạy trực tiếp.
    # Vai trò: Phục vụ môi trường phát triển; khi Deploy Render sẽ chạy qua Gunicorn.
    print("=" * 60)
    print(f"{BOT_NAME} khởi động")
    print(f"PORT: {PORT}")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
    )
