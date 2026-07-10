from flask import Flask, request, jsonify
from flask_cors import CORS

from config import PORT, check_config
from services.router_service import route_message_for_ai, get_welcome_message
from services.gemini_service import ask_gemini_status
from services.zalo_service import send_zalo_text
from services.logger import (
    write_log,
    log_error,
    debug_log,
    write_unknown_log,
    log_ai_event,
    log_ai_fallback,
)
from services.session_manager import get_context, save_context, clear_context
from services.sheet_api import read_setting_system, read_setting_chat, read_setting_ai

app = Flask(__name__)
CORS(app)

processed_messages = set()
MAX_PROCESSED_MESSAGES = 5000


# Chức năng: Lấy giá trị cấu hình hội thoại từ sheet SETTING_CHAT.
# Vai trò: Không để nội dung trả lời nằm cứng trong app.py.
def get_chat_setting(key, default=""):
    data = read_setting_chat() or {}
    return str(data.get(key) or default or "").strip()


# Chức năng: Lấy giá trị cấu hình hệ thống từ sheet SETTING_SYSTEM.
# Vai trò: Không để tên BOT hoặc thông tin đơn vị nằm cứng trong app.py.
def get_system_setting(key, default=""):
    data = read_setting_system() or {}
    return str(data.get(key) or default or "").strip()


# Chức năng: Lấy giá trị cấu hình AI từ sheet SETTING_AI.
# Vai trò: Điều khiển Gemini như lớp mở rộng tùy chọn, không phải luồng chính.
def get_ai_setting(key, default=""):
    data = read_setting_ai() or {}
    return str(data.get(key) or default or "").strip()


# Chức năng: Chuyển cấu hình dạng chữ thành boolean.
# Vai trò: Đọc các cờ bật/tắt từ Google Sheets một cách ổn định.
def is_enabled(value, default=False):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled", "bat", "bật", "co", "có"}


# Chức năng: Tạo câu trả lời mặc định khi BOT không xác định được dữ liệu.
# Vai trò: Lấy fallback từ SETTING_CHAT, không để nghiệp vụ nằm trong app.py.
def get_default_reply():
    return get_chat_setting("UNKNOWN_MESSAGE", "BOT chưa có dữ liệu phù hợp trong Google Sheets.")


# Chức năng: Tạo thông báo khi AI tạm thời không khả dụng.
# Vai trò: Bảo đảm lỗi Gemini không làm gián đoạn luồng chính Google Sheets.
def get_ai_unavailable_message():
    return get_chat_setting("AI_UNAVAILABLE_MESSAGE", get_default_reply())


# Chức năng: Tạo ghi chú khi câu trả lời do AI hỗ trợ.
# Vai trò: Lấy cảnh báo AI từ SETTING_CHAT, không hardcode nội dung nghiệp vụ.
def get_ai_notice():
    return get_chat_setting("AI_NOTICE", "")


# Chức năng: Kiểm tra BOT có được phép gọi Gemini hay không.
# Vai trò: Thực thi nguyên tắc AI optional, Google Sheets là luồng chính.
def can_use_ai(routed):
    if not is_enabled(get_ai_setting("AI_ENABLED", "TRUE"), True):
        return False

    if is_enabled(get_ai_setting("AI_IS_CORE", "FALSE"), False):
        return False

    if not bool(routed.get("use_ai", False)):
        return False

    ai_context = str(routed.get("ai_context") or "").strip()
    source = str(routed.get("source") or "").strip().upper()

    if ai_context:
        return is_enabled(get_ai_setting("ENABLE_AI_SUMMARIZE", "TRUE"), True)

    if source in {"DEFAULT", "UNKNOWN", "AI_FALLBACK", "ROUTER_ERROR"}:
        return (
            is_enabled(get_ai_setting("ENABLE_AI_GENERAL_KNOWLEDGE", "FALSE"), False)
            and is_enabled(get_ai_setting("ALLOW_AI_WITHOUT_SHEET_CONTEXT", "FALSE"), False)
        )

    return False


# Chức năng: Ghi log hội thoại với khả năng tương thích logger mới.
# Vai trò: Tránh lỗi ghi log làm ảnh hưởng phản hồi chính cho người dân.
def write_log_safe(
    user_id,
    user_message,
    bot_reply,
    source="BOT",
    route="",
    score="",
    sheet="",
    row_id="",
    note="",
    ai_status="",
    ai_model="",
    ai_called="",
):
    try:
        return write_log(
            user_id=user_id,
            user_message=user_message,
            bot_reply=bot_reply,
            source=source,
            route=route,
            score=score,
            sheet=sheet,
            row_id=row_id,
            note=note,
            ai_status=ai_status,
            ai_model=ai_model,
            ai_called=ai_called,
        )
    except TypeError:
        return write_log(user_id=user_id, user_message=user_message, bot_reply=bot_reply, source=source)


# Chức năng: Ghi nhận câu hỏi chưa có dữ liệu phù hợp.
# Vai trò: Tạo nguồn bổ sung dữ liệu vào Google Sheets sau kiểm thử.
def log_unknown_safe(user_id, question, route="UNKNOWN", note="NO_SHEET_MATCH", ai_called="", ai_status=""):
    try:
        return write_unknown_log(
            user_id=user_id,
            user_message=question,
            route=route,
            note=note,
            ai_called=ai_called,
            ai_status=ai_status,
        )
    except Exception as e:
        print(f"[UNKNOWN LOG ERROR] {e}")
        return False


# Chức năng: Kiểm tra và ghi nhớ message_id đã xử lý.
# Vai trò: Chống xử lý trùng webhook Zalo.
def remember_message(message_id):
    if not message_id:
        return False
    if message_id in processed_messages:
        return True
    processed_messages.add(message_id)
    if len(processed_messages) > MAX_PROCESSED_MESSAGES:
        processed_messages.clear()
    return False


# Chức năng: Gọi Gemini theo cơ chế tùy chọn và nhận trạng thái AI.
# Vai trò: Nếu Gemini lỗi, hết quota hoặc timeout thì quay về câu trả lời từ Google Sheets.
def try_ai_answer(user_id, question, routed, fallback_answer):
    if not can_use_ai(routed):
        return fallback_answer, routed.get("source", "DEFAULT"), "AI_NOT_USED", ""

    ai_context = routed.get("ai_context", "")
    ai_model = get_ai_setting("GEMINI_MODEL", get_ai_setting("MODEL", ""))

    try:
        result = ask_gemini_status(question, context=ai_context)
        ai_status = str(result.get("ai_status") or "UNKNOWN").strip()
        ai_error = str(result.get("error") or "").strip()
        ai_text = str(result.get("text") or "").strip()

        if result.get("ok") and ai_text and ai_text != get_default_reply():
            answer = ai_text
            notice = get_ai_notice()
            if notice:
                answer = answer + "\\n\\n────────────────\\n" + notice

            log_ai_event(
                user_id=user_id,
                user_message=question,
                ai_status=ai_status or "ONLINE",
                ai_model=ai_model,
                bot_reply=answer,
                route="AI_OK",
                note="AI_OPTIONAL_SUCCESS",
            )
            return answer, "GEMINI_AI", ai_status or "ONLINE", ai_model

        fallback = fallback_answer or ai_text or get_ai_unavailable_message()
        log_ai_fallback(
            user_id=user_id,
            user_message=question,
            ai_status=ai_status or "AI_FALLBACK",
            fallback_message=fallback,
            route="AI_FALLBACK",
            ai_model=ai_model,
            note=ai_error or "AI_OPTIONAL_FALLBACK",
        )
        return fallback, "AI_FALLBACK", ai_status or "AI_FALLBACK", ai_model

    except Exception as e:
        print(f"[AI OPTIONAL ERROR] {e}")
        fallback = fallback_answer or get_ai_unavailable_message()
        log_ai_fallback(
            user_id=user_id,
            user_message=question,
            ai_status="API_ERROR",
            fallback_message=fallback,
            route="AI_EXCEPTION",
            ai_model=ai_model,
            note=str(e),
        )
        return fallback, "AI_UNAVAILABLE", "API_ERROR", ai_model


# Chức năng: Xây dựng câu trả lời cho một tin nhắn người dân.
# Vai trò: Điều phối session, router, Gemini optional, log và không xử lý nghiệp vụ trực tiếp.
def build_answer(user_id, question):
    context = get_context(user_id)

    debug_log("INPUT", {
        "user_id": user_id,
        "question": question,
        "context_before": context,
    })

    routed = route_message_for_ai(question, context=context)

    debug_log("ROUTER_RESULT", {
        "reply": routed.get("reply"),
        "source": routed.get("source"),
        "use_ai": routed.get("use_ai"),
        "context_after": routed.get("context"),
        "ai_context": routed.get("ai_context"),
        "unknown_log": routed.get("unknown_log"),
    })

    answer = routed.get("reply") or get_default_reply()
    source = routed.get("source", "DEFAULT")
    new_context = routed.get("context", context)
    ai_status = "AI_NOT_REQUESTED"
    ai_model = ""

    if source == "RESET":
        clear_context(user_id)
    elif source == "WELCOME":
        save_context(user_id, {})
    else:
        save_context(user_id, new_context)

    answer, source, ai_status, ai_model = try_ai_answer(user_id, question, routed, answer)

    if routed.get("unknown_log") or source in {"DEFAULT", "UNKNOWN", "AI_FALLBACK", "AI_UNAVAILABLE"}:
        log_unknown_safe(
            user_id=user_id,
            question=question,
            route=source,
            note=str(ai_status or "NO_SHEET_MATCH"),
            ai_called=source in {"GEMINI_AI", "AI_FALLBACK", "AI_UNAVAILABLE"},
            ai_status=ai_status,
        )

    write_log_safe(
        user_id=user_id,
        user_message=question,
        bot_reply=answer,
        source=source,
        route=source,
        note=ai_status,
        ai_status=ai_status,
        ai_model=ai_model,
        ai_called=source in {"GEMINI_AI", "AI_FALLBACK", "AI_UNAVAILABLE"},
    )

    debug_log("FINAL_ANSWER", {
        "source": source,
        "ai_status": ai_status,
        "answer": answer,
    })

    return answer, source


# Chức năng: Trả trạng thái cơ bản của ứng dụng.
# Vai trò: Phục vụ kiểm tra nhanh BOT sau khi deploy.
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "bot": get_system_setting("BOT_NAME", "BOT CAP"),
        "version": get_system_setting("BOT_VERSION", "3.1"),
        "data_source": get_system_setting("DATA_SOURCE", "GOOGLE_SHEETS"),
        "ai_mode": get_ai_setting("AI_MODE", "OPTIONAL"),
        "message": "Bot đang hoạt động",
    })


# Chức năng: Kiểm tra cấu hình deploy và nguồn dữ liệu.
# Vai trò: Hỗ trợ phát hiện thiếu biến môi trường hoặc sai cấu hình hệ thống.
@app.route("/health", methods=["GET"])
def health():
    ok, missing = check_config()
    return jsonify({
        "status": "ok" if ok else "missing_config",
        "missing": missing,
        "data_source": get_system_setting("DATA_SOURCE", "GOOGLE_SHEETS"),
        "use_knowledge_json": get_system_setting("USE_KNOWLEDGE_JSON", "FALSE"),
        "ai_mode": get_ai_setting("AI_MODE", "OPTIONAL"),
        "ai_is_core": get_ai_setting("AI_IS_CORE", "FALSE"),
        "ai_enabled": get_ai_setting("AI_ENABLED", "TRUE"),
        "ai_status": get_ai_setting("AI_STATUS", "ONLINE"),
    })


# Chức năng: Kiểm thử hội thoại qua trình duyệt hoặc Postman.
# Vai trò: Cho phép test nhanh router, AI optional và session.
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


# Chức năng: Cung cấp API chat nội bộ.
# Vai trò: Hỗ trợ kiểm thử ngoài Zalo mà vẫn đi qua cùng một luồng xử lý.
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "web")
    question = data.get("question", "")

    if not question:
        return jsonify({"success": False, "message": "Missing question"}), 400

    answer, source = build_answer(user_id=user_id, question=question)
    return jsonify({"success": True, "answer": answer, "source": source})


# Chức năng: Nhận webhook từ Zalo OA.
# Vai trò: Chuyển tin nhắn người dân vào luồng xử lý BOT CAP 3.1.
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
                send_zalo_text(user_id=user_id, message=get_default_reply())
            log_error(user_id=user_id, user_message=question, error_message=error_message)
        except Exception as log_e:
            print("[WEBHOOK LOG ERROR]", log_e)

        return jsonify({"success": False, "message": str(e)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
