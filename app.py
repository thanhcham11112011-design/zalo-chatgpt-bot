import hmac
import os
import time

from flask import Flask, request, jsonify

from config import PORT, INTERNAL_API_KEY, check_config
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
from services.sheet_api import (
    read_setting_system,
    read_setting_chat,
    read_setting_ai,
    sheet_health,
    get_sheet_cache_status,
)


HEALTH_CHECK_TTL_SECONDS = int(
    os.getenv("HEALTH_CHECK_TTL_SECONDS", "300")
)

_health_check_cache = {
    "checked_at": 0.0,
    "result": None,
}

app = Flask(__name__)

processed_messages = set()
MAX_PROCESSED_MESSAGES = 5000

# Chức năng: Kiểm tra khóa bảo vệ API nội bộ từ HTTP header.
# Vai trò: Ngăn người ngoài gọi test-ai và api-chat để tiêu hao tài nguyên BOT.
def is_internal_api_authorized():
    provided_key = request.headers.get("X-Internal-API-Key", "").strip()

    if not INTERNAL_API_KEY or not provided_key:
        return False

    return hmac.compare_digest(provided_key, INTERNAL_API_KEY)

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

# Chức năng: Lấy kết quả kiểm tra Google Sheets có cache giới hạn tần suất.
# Vai trò: Tránh route health check liên tục gọi Google Sheets và gây vượt quota đọc.
def _get_cached_sheet_health():
    now = time.time()
    checked_at = float(
        _health_check_cache.get("checked_at") or 0
    )
    result = _health_check_cache.get("result")

    is_cached = (
        result is not None
        and now - checked_at < HEALTH_CHECK_TTL_SECONDS
    )

    if not is_cached:
        result = sheet_health()
        checked_at = now
        _health_check_cache["checked_at"] = checked_at
        _health_check_cache["result"] = result

    age_seconds = max(0, int(now - checked_at))

    return result, is_cached, age_seconds


# Chức năng: Trả trạng thái cơ bản của ứng dụng Flask.
# Vai trò: Xác nhận dịch vụ Render đang chạy mà không gọi Google Sheets.
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "service": "online",
        "message": "Ứng dụng Flask đang hoạt động",
    }), 200


# Chức năng: Kiểm tra cấu hình, Google Sheets, cấu trúc dữ liệu và cache dự phòng.
# Vai trò: Phân loại hệ thống thành healthy, degraded hoặc unhealthy.
@app.route("/health", methods=["GET"])
def health():
    config_ok, missing_config = check_config()
    sheet_result, health_cached, health_age = (
        _get_cached_sheet_health()
    )
    cache_status = get_sheet_cache_status()

    sheet_ok = bool(sheet_result.get("ok"))
    sheet_error = str(sheet_result.get("error") or "")
    missing_sheets = list(
        sheet_result.get("missing") or []
    )
    sheet_errors = list(
        sheet_result.get("errors") or []
    )

    if not config_ok:
        status = "unhealthy"
        reason = "missing_config"
        http_status = 503

    elif sheet_ok:
        status = "healthy"
        reason = "system_ready"
        http_status = 200

    elif sheet_error and cache_status.get("has_data"):
        status = "degraded"
        reason = "google_sheets_error_using_cache"
        http_status = 207

    else:
        status = "unhealthy"
        reason = "google_sheets_or_schema_error"
        http_status = 503

    return jsonify({
        "status": status,
        "reason": reason,
        "service": "online",
        "config": {
            "ok": config_ok,
            "missing": missing_config,
        },
        "google_sheets": {
            "ok": sheet_ok,
            "using_cache": status == "degraded",
            "missing_sheets": missing_sheets,
            "errors": sheet_errors,
            "error": sheet_error,
        },
        "cache": {
            "available": cache_status.get(
                "available",
                False,
            ),
            "has_data": cache_status.get(
                "has_data",
                False,
            ),
            "sheet_count": cache_status.get(
                "sheet_count",
                0,
            ),
            "valid_sheet_count": cache_status.get(
                "valid_sheet_count",
                0,
            ),
            "data_sheet_count": cache_status.get(
                "data_sheet_count",
                0,
            ),
            "fresh_sheet_count": cache_status.get(
                "fresh_sheet_count",
                0,
            ),
            "fallback_sheet_count": cache_status.get(
                "fallback_sheet_count",
                0,
            ),
            "expired_sheet_count": cache_status.get(
                "expired_sheet_count",
                0,
            ),
            "oldest_age_seconds": cache_status.get(
                "oldest_age_seconds",
                0,
            ),
            "ttl_seconds": cache_status.get(
                "ttl_seconds",
                0,
            ),
            "max_stale_seconds": cache_status.get(
                "max_stale_seconds",
                0,
            ),
        },
        "health_check": {
            "cached": health_cached,
            "age_seconds": health_age,
            "ttl_seconds": HEALTH_CHECK_TTL_SECONDS,
        },
    }), http_status
        
# Chức năng: Kiểm thử hội thoại qua trình duyệt hoặc Postman.
# Vai trò: Cho phép test nhanh router, AI optional và session.
@app.route("/test-ai", methods=["GET", "POST"])
def test_ai():
    if not is_internal_api_authorized():
        return jsonify({
            "success": False,
            "message": "Unauthorized",
        }), 401

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
    if not is_internal_api_authorized():
        return jsonify({
            "success": False,
            "message": "Unauthorized",
        }), 401

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
        event_name = data.get("event_name", "")
        user_id = data.get("sender", {}).get("id", "") or data.get("user_id_by_app", "")
        message_data = data.get("message", {}) or {}

        if not user_id:
            return jsonify({"success": False, "message": "Missing user_id"}), 400

        if event_name != "user_send_text":
            return jsonify({"success": True, "message": "Event ignored"}), 200

        message_id = message_data.get("msg_id") or message_data.get("message_id") or ""
        if remember_message(message_id):
            return jsonify({"success": True, "message": "Duplicate ignored"}), 200

        question = message_data.get("text", "")
        if not question:
            sent = send_zalo_text(
                user_id=user_id,
                message=get_welcome_message(),
            )

            if not sent:
                error_message = "Gửi tin nhắn chào mừng Zalo thất bại."
                print("[ZALO SEND ERROR]", error_message)
                log_error(
                    user_id=user_id,
                    user_message="",
                    error_message=error_message,
                    route="ZALO_SEND_ERROR",
                    note="EMPTY_TEXT_REPLY",
                    error_code="ZALO_SEND_FAILED",
                )
                return jsonify({
                    "success": False,
                    "message": "Zalo send failed",
                }), 200

            return jsonify({
                "success": True,
                "message": "Empty text handled",
            }), 200

        answer, source = build_answer(
            user_id=user_id,
            question=question,
        )

        sent = send_zalo_text(
            user_id=user_id,
            message=answer,
        )

        if not sent:
            error_message = "Gửi câu trả lời Zalo thất bại."
            print("[ZALO SEND ERROR]", error_message)
            log_error(
                user_id=user_id,
                user_message=question,
                error_message=error_message,
                route="ZALO_SEND_ERROR",
                note=f"SOURCE={source}",
                error_code="ZALO_SEND_FAILED",
            )
            return jsonify({
                "success": False,
                "message": "Zalo send failed",
                "source": source,
            }), 200

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
            user_id = data.get("sender", {}).get("id", "")
            question = data.get("message", {}).get("text", "")

            if user_id:
                fallback_sent = send_zalo_text(
                    user_id=user_id,
                    message=get_default_reply(),
                )
                if not fallback_sent:
                    print(
                        "[ZALO FALLBACK SEND ERROR]",
                        "Không gửi được thông báo dự phòng.",
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
    app.run(host="0.0.0.0", port=PORT)
