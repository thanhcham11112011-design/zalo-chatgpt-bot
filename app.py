from flask import Flask, request, jsonify
from flask_cors import CORS

from config import PORT, BOT_NAME, DEFAULT_REPLY, check_config
from services.router_service import route_message_for_ai, get_welcome_message
from services.gemini_service import ask_gemini
from services.zalo_service import send_zalo_text
from services.logger import write_log, log_error
from services.session_manager import get_context, save_context, clear_context

app = Flask(__name__)
CORS(app)
processed_messages = set()
MAX_PROCESSED_MESSAGES = 5000


def remember_message(message_id):
    if not message_id:
        return False
    if message_id in processed_messages:
        return True
    processed_messages.add(message_id)
    if len(processed_messages) > MAX_PROCESSED_MESSAGES:
        processed_messages.clear()
    return False


def build_answer(user_id, question):
    context = get_context(user_id)

    routed = route_message_for_ai(
        question,
        context=context
    )

    answer = routed.get("reply", DEFAULT_REPLY)
    source = routed.get("source", "DEFAULT")
    use_ai = routed.get("use_ai", False)

    if "context" in routed:
        new_context = routed["context"]
    else:
        new_context = context

    ai_context = routed.get("ai_context", "")

    if source == "RESET":
        clear_context(user_id)
    elif source == "WELCOME":
        save_context(user_id, {})
    else:
        save_context(user_id, new_context)

    if use_ai:
        ai_answer = ask_gemini(question, context=ai_context)

        if ai_answer and ai_answer.strip() != DEFAULT_REPLY:
            answer = (
                ai_answer.strip()
                + "\n\n────────────────\n"
                + "🤖 Lưu ý: Trợ lý AI Công an phường Phù Liễn chủ yếu hỗ trợ thủ tục hành chính, căn cước, cư trú, VNeID, phản ánh ANTT và tra cứu cơ quan thực hiện.\n"
                + "Quý công dân có thể nhắn 'menu' để xem danh mục hỗ trợ."
            )
            source = "GEMINI_AI"
        else:
            answer = (
                "Xin lỗi, hiện tôi chưa hiểu rõ ý định câu hỏi hoặc hệ thống AI đang tạm thời không khả dụng.\n\n"
                "Quý công dân vui lòng nhập rõ nội dung cần hỗ trợ, ví dụ:\n"
                "• Làm căn cước ở đâu\n"
                "• Đăng ký tạm trú cần giấy tờ gì\n"
                "• Số điện thoại Công an phường\n"
                "• menu"
            )
            source = "AI_FALLBACK"

    write_log(
        user_id=user_id,
        user_message=question,
        bot_reply=answer,
        source=source
    )

    return answer, source


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "bot": BOT_NAME, "message": "Bot đang hoạt động"})


@app.route("/health", methods=["GET"])
def health():
    ok, missing = check_config()
    return jsonify({"status": "ok" if ok else "missing_config", "missing": missing})


@app.route("/test-ai", methods=["GET", "POST"])
def test_ai():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        question = data.get("question", "")
        user_id = data.get("user_id", "test-web")
    else:
        question = request.args.get("q", "menu")
        user_id = request.args.get("user_id", "test-web")
    answer, source = build_answer(user_id=user_id, question=question)
    return jsonify({"success": True, "question": question, "answer": answer, "source": source})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "web")
    question = data.get("question", "")
    if not question:
        return jsonify({"success": False, "message": "Missing question"}), 400
    answer, source = build_answer(user_id=user_id, question=question)
    return jsonify({"success": True, "answer": answer, "source": source})


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "ok", "message": "Webhook OK"}), 200

    data = request.get_json(silent=True) or {}

    try:
        print("WEBHOOK DATA:", data)
        event_name = data.get("event_name", "")
        user_id = data.get("sender", {}).get("id", "") or data.get("user_id_by_app", "")
        message_data = data.get("message", {}) or {}

        if not user_id:
            return jsonify({"success": False, "message": "Missing user_id"}), 400

        if event_name != "user_send_text":
            send_zalo_text(user_id=user_id, message=get_welcome_message())
            return jsonify({"success": True, "message": "Non-text event handled"}), 200

        message_id = message_data.get("msg_id") or message_data.get("message_id") or ""
        if remember_message(message_id):
            return jsonify({"success": True, "message": "Duplicate ignored"}), 200

        question = message_data.get("text", "")
        if not question:
            send_zalo_text(user_id=user_id, message=get_welcome_message())
            return jsonify({"success": True, "message": "Empty text handled"}), 200

        answer, source = build_answer(user_id=user_id, question=question)
        send_zalo_text(user_id=user_id, message=answer)
        return jsonify({"success": True, "source": source}), 200

    except Exception as e:
        import traceback
        error_message = f"Lỗi xử lý webhook: {e}"
        print("[WEBHOOK ERROR]", error_message)
        print(traceback.format_exc())
        try:
            user_id = data.get("sender", {}).get("id", "")
            question = data.get("message", {}).get("text", "")
            if user_id:
                send_zalo_text(user_id=user_id, message=DEFAULT_REPLY)
            log_error(user_id=user_id, user_message=question, error_message=error_message)
        except Exception as log_e:
            print("[WEBHOOK LOG ERROR]", log_e)
        return jsonify({"success": False, "message": str(e)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
