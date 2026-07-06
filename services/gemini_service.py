import time

from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL
from services.sheet_api import read_prompt, read_setting_ai, read_setting_chat

_client = None
_client_key = ""


# Chức năng: Lấy giá trị cấu hình theo nhiều biến thể tên khóa.
# Vai trò: Giúp Gemini Service đọc linh hoạt dữ liệu từ Google Sheets.
def _get_setting(data, *keys, default=""):
    for key in keys:
        value = str((data or {}).get(key) or "").strip()
        if value:
            return value
    return str(default or "").strip()


# Chức năng: Chuyển giá trị cấu hình dạng chuỗi về boolean.
# Vai trò: Chuẩn hóa các cờ bật/tắt AI đọc từ Google Sheets.
def _as_bool(value, default=False):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "bat", "bật", "co", "có"}


# Chức năng: Chuyển giá trị cấu hình dạng chuỗi về số nguyên.
# Vai trò: Chuẩn hóa timeout, retry và giới hạn ký tự của AI.
def _as_int(value, default=0):
    try:
        return int(str(value).strip())
    except Exception:
        return default


# Chức năng: Lấy thông báo hội thoại từ SETTING_CHAT.
# Vai trò: Không để câu trả lời mặc định nằm cứng trong Python.
def _get_chat_message(key, default=""):
    try:
        return _get_setting(read_setting_chat(), key, default=default)
    except Exception:
        return str(default or "").strip()


# Chức năng: Lấy prompt điều khiển AI từ sheet PROMPT.
# Vai trò: Đưa toàn bộ prompt nghiệp vụ ra Google Sheets.
def _get_prompt_value(key, default=""):
    try:
        return _get_setting(read_prompt(), key, default=default)
    except Exception:
        return str(default or "").strip()


# Chức năng: Đọc toàn bộ cấu hình AI từ SETTING_AI.
# Vai trò: Điều khiển Gemini theo mô hình AI Optional của BOT CAP 3.1.
def _read_ai_settings():
    try:
        return read_setting_ai() or {}
    except Exception:
        return {}


# Chức năng: Đọc cấu hình Gemini từ SETTING_AI và biến môi trường.
# Vai trò: Tách cấu hình AI khỏi nghiệp vụ và cho phép điều chỉnh bằng Google Sheets.
def _get_ai_config():
    settings = _read_ai_settings()
    api_key = _get_setting(settings, "GEMINI_API_KEY", "API_KEY", default=GEMINI_API_KEY)
    model = _get_setting(settings, "GEMINI_MODEL", "MODEL", default=GEMINI_MODEL or "gemini-2.0-flash")
    return api_key, model


# Chức năng: Kiểm tra AI có được phép hoạt động không.
# Vai trò: Bảo đảm Gemini chỉ là luồng phụ, có thể tắt mà không ảnh hưởng BOT chính.
def _ai_allowed(context=""):
    settings = _read_ai_settings()
    ai_enabled = _as_bool(_get_setting(settings, "AI_ENABLED", default="TRUE"), True)
    ai_mode = _get_setting(settings, "AI_MODE", default="OPTIONAL").upper()
    ai_status = _get_setting(settings, "AI_STATUS", default="ONLINE").upper()
    allow_without_context = _as_bool(_get_setting(settings, "ALLOW_AI_PROCEDURE_WITHOUT_DATA", default="FALSE"), False)

    if not ai_enabled:
        return False, "DISABLED"
    if ai_mode not in {"OPTIONAL", "ON", "ENABLE", "ENABLED"}:
        return False, "DISABLED"
    if ai_status in {"OFF", "OFFLINE", "DISABLED", "QUOTA_EXCEEDED", "ERROR"}:
        return False, ai_status
    if not str(context or "").strip() and not allow_without_context:
        return False, "NO_SHEET_CONTEXT"
    return True, "ONLINE"


# Chức năng: Khởi tạo Gemini client theo API key đang cấu hình.
# Vai trò: Cung cấp kết nối AI phụ trợ cho BOT khi AI được phép bật.
def _get_client():
    global _client, _client_key

    api_key, _ = _get_ai_config()
    if not api_key:
        return None

    if _client and _client_key == api_key:
        return _client

    _client = genai.Client(api_key=api_key)
    _client_key = api_key
    return _client


# Chức năng: Lấy câu fallback từ SETTING_CHAT.
# Vai trò: Bảo đảm Gemini Service không hardcode nội dung trả lời nghiệp vụ.
def _fallback_reply(status="AI_FALLBACK"):
    if status in {"DISABLED", "OFFLINE", "QUOTA_EXCEEDED", "TIMEOUT", "API_ERROR"}:
        msg = _get_chat_message("AI_UNAVAILABLE_MESSAGE", "")
        if msg:
            return msg
    return _get_chat_message(
        "UNKNOWN_MESSAGE",
        "Xin lỗi, hiện hệ thống chưa có đủ dữ liệu phù hợp để trả lời. Quý công dân vui lòng nhắn 'menu' để xem danh mục hỗ trợ.",
    )


# Chức năng: Phân loại lỗi Gemini thành trạng thái kỹ thuật.
# Vai trò: Giúp BOT ghi log AI và tự fallback khi hết quota, timeout hoặc lỗi API.
def _classify_error(error):
    text = str(error or "").lower()
    if "quota" in text or "resource exhausted" in text or "429" in text or "billing" in text:
        return "QUOTA_EXCEEDED"
    if "timeout" in text or "timed out" in text or "deadline" in text:
        return "TIMEOUT"
    if "api key" in text or "permission" in text or "unauthorized" in text:
        return "API_ERROR"
    return "API_ERROR"


# Chức năng: Tạo prompt gửi Gemini từ PROMPT và dữ liệu tham khảo.
# Vai trò: AI chỉ tổng hợp theo dữ liệu Google Sheets, không tự sinh nghiệp vụ.
def build_prompt(question, context=""):
    system_prompt = _get_prompt_value(
        "SYSTEM",
        "Bạn là trợ lý AI hỗ trợ người dân. Chỉ trả lời theo dữ liệu được cung cấp; không suy diễn nghiệp vụ khi không có căn cứ.",
    )
    ai_policy = _get_prompt_value(
        "AI_POLICY",
        "Không sử dụng knowledge.json. Không bịa thủ tục, số điện thoại, địa chỉ, cán bộ, lệ phí, thời hạn hoặc căn cứ pháp lý.",
    )
    response_rule = _get_prompt_value(
        "RESPONSE_RULE",
        "Trả lời ngắn gọn, lịch sự, dễ hiểu; ưu tiên nội dung có trong dữ liệu tham khảo.",
    )

    question = str(question or "").strip()
    context = str(context or "").strip()

    parts = [system_prompt, "", "QUY TẮC BOT CAP 3.1:", ai_policy, response_rule]

    if context:
        parts.extend([
            "",
            "DỮ LIỆU THAM KHẢO TỪ GOOGLE SHEETS:",
            context,
            "",
            "YÊU CẦU:",
            "Chỉ tổng hợp theo dữ liệu tham khảo. Không tự bổ sung thông tin ngoài Google Sheets.",
        ])
    else:
        parts.extend([
            "",
            "YÊU CẦU:",
            "Không có dữ liệu tham khảo từ Google Sheets. Không suy diễn nghiệp vụ.",
        ])

    parts.extend(["", "CÂU HỎI CỦA NGƯỜI DÂN:", question, "", "GIỚI HẠN:", "Không quá 1500 ký tự."])
    return "\n".join(parts).strip()


# Chức năng: Gửi câu hỏi tới Gemini và trả về cả nội dung lẫn trạng thái AI.
# Vai trò: Hỗ trợ app/logger nhận biết ONLINE, DISABLED, QUOTA_EXCEEDED, TIMEOUT, API_ERROR.
def ask_gemini_status(question, context=""):
    allowed, status = _ai_allowed(context=context)
    if not allowed:
        return {"ok": False, "text": _fallback_reply(status), "ai_status": status, "error": ""}

    settings = _read_ai_settings()
    retry_count = max(_as_int(_get_setting(settings, "AI_RETRY_COUNT", default="1"), 1), 1)
    max_output_chars = max(_as_int(_get_setting(settings, "AI_MAX_OUTPUT_CHARS", default="1500"), 1500), 300)

    try:
        client = _get_client()
        _, model = _get_ai_config()
        if not client:
            return {"ok": False, "text": _fallback_reply("DISABLED"), "ai_status": "DISABLED", "error": "MISSING_API_KEY"}

        last_error = ""
        for attempt in range(retry_count):
            try:
                response = client.models.generate_content(model=model, contents=build_prompt(question, context))
                text = str(getattr(response, "text", "") or "").strip()
                if text:
                    return {"ok": True, "text": text[:max_output_chars], "ai_status": "ONLINE", "error": ""}
                last_error = "EMPTY_RESPONSE"
            except Exception as e:
                last_error = str(e)
                status = _classify_error(e)
                if status == "QUOTA_EXCEEDED":
                    break
                if attempt < retry_count - 1:
                    time.sleep(0.5)

        final_status = _classify_error(last_error)
        print(f"[GEMINI ERROR] {final_status}: {last_error}")
        return {"ok": False, "text": _fallback_reply(final_status), "ai_status": final_status, "error": last_error}

    except Exception as e:
        final_status = _classify_error(e)
        print(f"[GEMINI ERROR] {final_status}: {e}")
        return {"ok": False, "text": _fallback_reply(final_status), "ai_status": final_status, "error": str(e)}


# Chức năng: Gửi câu hỏi tới Gemini khi router cần AI phụ trợ.
# Vai trò: Giữ tương thích với app.py cũ, chỉ trả về nội dung văn bản.
def ask_gemini(question, context=""):
    result = ask_gemini_status(question, context=context)
    return result.get("text") or _fallback_reply(result.get("ai_status", "AI_FALLBACK"))
