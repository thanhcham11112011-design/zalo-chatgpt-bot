import time

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL
from services.console_logger import console_log
from services.sheet_api import (
    read_prompt,
    read_setting_ai,
    read_setting_chat,
)

_client = None
_client_signature = ()


# Chức năng: Lấy giá trị cấu hình theo đúng khóa chuẩn trong SETTING_AI.
# Vai trò: Không duy trì nhiều tên khóa cạnh tranh cho cùng một cấu hình AI.
def _get_setting(data, key, default=""):
    value = str((data or {}).get(key) or "").strip()
    return value if value else str(default or "").strip()


# Chức năng: Chuyển giá trị cấu hình dạng chuỗi về boolean.
# Vai trò: Chuẩn hóa các cờ bật/tắt AI đọc từ Google Sheets.
def _as_bool(value, default=False):
    if value is None or str(value).strip() == "":
        return default

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "bat",
        "bật",
        "co",
        "có",
    }


# Chức năng: Chuyển giá trị cấu hình dạng chuỗi về số nguyên.
# Vai trò: Chuẩn hóa timeout, retry và giới hạn đầu ra AI.
def _as_int(value, default=0, minimum=None, maximum=None):
    try:
        number = int(str(value).strip())
    except Exception:
        number = int(default)

    if minimum is not None:
        number = max(number, minimum)

    if maximum is not None:
        number = min(number, maximum)

    return number


# Chức năng: Chuyển giá trị cấu hình dạng chuỗi về số thực.
# Vai trò: Chuẩn hóa TEMPERATURE và TOP_P trước khi gọi Gemini.
def _as_float(value, default=0.0, minimum=None, maximum=None):
    try:
        number = float(str(value).strip())
    except Exception:
        number = float(default)

    if minimum is not None:
        number = max(number, minimum)

    if maximum is not None:
        number = min(number, maximum)

    return number


# Chức năng: Lấy thông báo hội thoại từ SETTING_CHAT.
# Vai trò: Không để câu trả lời mặc định nằm cứng trong Gemini Service.
def _get_chat_message(key, default=""):
    try:
        return _get_setting(
            read_setting_chat(),
            key,
            default=default,
        )
    except Exception:
        return str(default or "").strip()


# Chức năng: Lấy prompt điều khiển AI từ sheet PROMPT.
# Vai trò: Đưa toàn bộ prompt nghiệp vụ ra Google Sheets.
def _get_prompt_value(key, default=""):
    try:
        return _get_setting(
            read_prompt(),
            key,
            default=default,
        )
    except Exception:
        return str(default or "").strip()


# Chức năng: Đọc toàn bộ cấu hình AI từ SETTING_AI.
# Vai trò: Dùng SETTING_AI làm nguồn vận hành Gemini duy nhất.
def _read_ai_settings():
    try:
        return read_setting_ai() or {}
    except Exception as e:
        console_log(
            "ERROR",
            "AI_CONFIG",
            "Không đọc được SETTING_AI",
            error=e,
        )
        return {}


# Chức năng: Đọc API key kỹ thuật và model chuẩn của Gemini.
# Vai trò: MODEL lấy từ SETTING_AI, API key chỉ lấy từ biến môi trường Render.
def _get_ai_config(settings=None):
    settings = settings or _read_ai_settings()
    model = _get_setting(
        settings,
        "MODEL",
        default=GEMINI_MODEL,
    )
    return GEMINI_API_KEY, model


# Chức năng: Chuẩn hóa toàn bộ tham số vận hành Gemini.
# Vai trò: Bảo đảm mọi lần gọi AI dùng cùng bộ cấu hình trong SETTING_AI.
def _get_runtime_config(settings=None):
    settings = settings or _read_ai_settings()

    return {
        "temperature": _as_float(
            _get_setting(settings, "TEMPERATURE", "0.2"),
            0.2,
            minimum=0.0,
            maximum=2.0,
        ),
        "top_p": _as_float(
            _get_setting(settings, "TOP_P", "0.9"),
            0.9,
            minimum=0.0,
            maximum=1.0,
        ),
        "top_k": _as_int(
            _get_setting(settings, "TOP_K", "40"),
            40,
            minimum=1,
        ),
        "max_output_tokens": _as_int(
            _get_setting(settings, "MAX_OUTPUT_TOKEN", "2048"),
            2048,
            minimum=1,
        ),
        "max_output_chars": _as_int(
            _get_setting(settings, "AI_MAX_OUTPUT_CHARS", "1500"),
            1500,
            minimum=300,
        ),
        "timeout_seconds": _as_int(
            _get_setting(settings, "AI_TIMEOUT_SECONDS", "15"),
            15,
            minimum=1,
        ),
        "retry_count": _as_int(
            _get_setting(settings, "AI_RETRY_COUNT", "1"),
            1,
            minimum=1,
            maximum=5,
        ),
    }


# Chức năng: Kiểm tra AI có được phép hoạt động không.
# Vai trò: Bảo đảm Gemini chỉ là lớp phụ trợ và tuân thủ cổng dữ liệu Google Sheets.
def _ai_allowed(context="", settings=None):
    settings = settings or _read_ai_settings()
    ai_enabled = _as_bool(
        _get_setting(settings, "AI_ENABLED", "TRUE"),
        True,
    )
    ai_mode = _get_setting(
        settings,
        "AI_MODE",
        "OPTIONAL",
    ).upper()
    ai_is_core = _as_bool(
        _get_setting(settings, "AI_IS_CORE", "FALSE"),
        False,
    )
    ai_status = _get_setting(
        settings,
        "AI_STATUS",
        "ONLINE",
    ).upper()
    strict_sheet_only = _as_bool(
        _get_setting(settings, "STRICT_SHEET_ONLY", "TRUE"),
        True,
    )
    allow_without_context = _as_bool(
        _get_setting(
            settings,
            "ALLOW_AI_WITHOUT_SHEET_CONTEXT",
            "FALSE",
        ),
        False,
    )

    if not ai_enabled or ai_is_core:
        return False, "DISABLED"

    if ai_mode != "OPTIONAL":
        return False, "DISABLED"

    if ai_status != "ONLINE":
        return False, ai_status or "OFFLINE"

    if not str(context or "").strip():
        if strict_sheet_only or not allow_without_context:
            return False, "NO_SHEET_CONTEXT"

    return True, "ONLINE"


# Chức năng: Khởi tạo Gemini client theo API key và timeout đang cấu hình.
# Vai trò: Tái tạo client khi timeout thay đổi mà không lưu API key vào Google Sheets.
def _get_client(settings=None, runtime=None):
    global _client, _client_signature

    settings = settings or _read_ai_settings()
    runtime = runtime or _get_runtime_config(settings)
    api_key, _ = _get_ai_config(settings)

    if not api_key:
        return None

    timeout_ms = runtime["timeout_seconds"] * 1000
    signature = (api_key, timeout_ms)

    if _client and _client_signature == signature:
        return _client

    try:
        http_options = types.HttpOptions(
            timeout=timeout_ms,
        )
    except Exception:
        http_options = {
            "timeout": timeout_ms,
        }

    try:
        _client = genai.Client(
            api_key=api_key,
            http_options=http_options,
        )
    except TypeError:
        console_log(
            "WARNING",
            "AI_CONFIG",
            "SDK hiện tại không hỗ trợ http_options tại Client",
            timeout_seconds=runtime["timeout_seconds"],
        )
        _client = genai.Client(
            api_key=api_key,
        )

    _client_signature = signature
    return _client


# Chức năng: Lấy câu fallback từ SETTING_CHAT.
# Vai trò: Bảo đảm Gemini lỗi không làm gián đoạn câu trả lời từ Google Sheets.
def _fallback_reply(status="AI_FALLBACK"):
    if status in {
        "DISABLED",
        "OFFLINE",
        "QUOTA_EXCEEDED",
        "TIMEOUT",
        "API_ERROR",
    }:
        message = _get_chat_message(
            "AI_UNAVAILABLE_MESSAGE",
            "",
        )

        if message:
            return message

    return _get_chat_message(
        "UNKNOWN_MESSAGE",
        (
            "Xin lỗi, hiện hệ thống chưa có đủ dữ liệu phù hợp để trả lời. "
            "Quý công dân vui lòng nhắn 'menu' để xem danh mục hỗ trợ."
        ),
    )


# Chức năng: Phân loại lỗi Gemini thành trạng thái kỹ thuật.
# Vai trò: Giúp BOT ghi log quota, timeout, cấu hình hoặc lỗi API thống nhất.
def _classify_error(error):
    text = str(error or "").lower()

    if (
        "quota" in text
        or "resource exhausted" in text
        or "resource_exhausted" in text
        or "429" in text
        or "billing" in text
    ):
        return "QUOTA_EXCEEDED"

    if (
        "timeout" in text
        or "timed out" in text
        or "deadline" in text
        or "deadline_exceeded" in text
    ):
        return "TIMEOUT"

    return "API_ERROR"


# Chức năng: Tạo prompt gửi Gemini từ PROMPT và dữ liệu tham khảo.
# Vai trò: AI chỉ tổng hợp theo dữ liệu Google Sheets và giới hạn ký tự cấu hình.
def build_prompt(question, context=""):
    settings = _read_ai_settings()
    runtime = _get_runtime_config(settings)
    system_prompt = _get_prompt_value(
        "SYSTEM",
        (
            "Bạn là trợ lý AI hỗ trợ người dân. Chỉ trả lời theo dữ liệu "
            "được cung cấp; không suy diễn nghiệp vụ khi không có căn cứ."
        ),
    )
    ai_policy = _get_prompt_value(
        "AI_POLICY",
        (
            "Không sử dụng knowledge.json. Không bịa thủ tục, số điện thoại, "
            "địa chỉ, cán bộ, lệ phí, thời hạn hoặc căn cứ pháp lý."
        ),
    )
    response_rule = _get_prompt_value(
        "RESPONSE_RULE",
        (
            "Trả lời ngắn gọn, lịch sự, dễ hiểu; ưu tiên nội dung có trong "
            "dữ liệu tham khảo."
        ),
    )

    question = str(question or "").strip()
    context = str(context or "").strip()
    parts = [
        system_prompt,
        "",
        "QUY TẮC BOT CAP 3.1:",
        ai_policy,
        response_rule,
    ]

    if context:
        parts.extend([
            "",
            "DỮ LIỆU THAM KHẢO TỪ GOOGLE SHEETS:",
            context,
            "",
            "YÊU CẦU:",
            (
                "Chỉ tổng hợp theo dữ liệu tham khảo. Không tự bổ sung "
                "thông tin ngoài Google Sheets."
            ),
        ])
    else:
        parts.extend([
            "",
            "YÊU CẦU:",
            (
                "Không có dữ liệu tham khảo từ Google Sheets. "
                "Không suy diễn nghiệp vụ."
            ),
        ])

    parts.extend([
        "",
        "CÂU HỎI CỦA NGƯỜI DÂN:",
        question,
        "",
        "GIỚI HẠN:",
        f"Không quá {runtime['max_output_chars']} ký tự.",
    ])
    return "\n".join(parts).strip()


# Chức năng: Gửi câu hỏi tới Gemini và trả về nội dung cùng trạng thái AI.
# Vai trò: Áp dụng thống nhất model, sampling, timeout, retry và giới hạn đầu ra.
def ask_gemini_status(question, context=""):
    settings = _read_ai_settings()
    allowed, status = _ai_allowed(
        context=context,
        settings=settings,
    )

    if not allowed:
        return {
            "ok": False,
            "text": _fallback_reply(status),
            "ai_status": status,
            "error": "",
        }

    runtime = _get_runtime_config(settings)
    api_key, model = _get_ai_config(settings)

    if not api_key:
        return {
            "ok": False,
            "text": _fallback_reply("DISABLED"),
            "ai_status": "DISABLED",
            "error": "MISSING_API_KEY",
        }

    if not model:
        console_log(
            "ERROR",
            "AI_CONFIG",
            "SETTING_AI thiếu khóa MODEL",
        )
        return {
            "ok": False,
            "text": _fallback_reply("DISABLED"),
            "ai_status": "DISABLED",
            "error": "MISSING_MODEL",
        }

    try:
        client = _get_client(
            settings=settings,
            runtime=runtime,
        )

        if not client:
            return {
                "ok": False,
                "text": _fallback_reply("DISABLED"),
                "ai_status": "DISABLED",
                "error": "MISSING_API_KEY",
            }

        generation_config = {
            "temperature": runtime["temperature"],
            "top_p": runtime["top_p"],
            "top_k": runtime["top_k"],
            "max_output_tokens": runtime["max_output_tokens"],
        }
        last_error = ""

        for attempt in range(1, runtime["retry_count"] + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=build_prompt(question, context),
                    config=generation_config,
                )
                text = str(
                    getattr(response, "text", "") or ""
                ).strip()

                if text:
                    return {
                        "ok": True,
                        "text": text[:runtime["max_output_chars"]],
                        "ai_status": "ONLINE",
                        "error": "",
                    }

                last_error = "EMPTY_RESPONSE"

            except Exception as e:
                last_error = str(e)
                error_status = _classify_error(e)

                if error_status == "QUOTA_EXCEEDED":
                    break

                if attempt < runtime["retry_count"]:
                    time.sleep(min(0.5 * attempt, 2.0))

        final_status = _classify_error(last_error)
        console_log(
            "ERROR",
            "GEMINI",
            "Yêu cầu Gemini thất bại",
            status=final_status,
            model=model,
            attempts=runtime["retry_count"],
            error=last_error,
        )
        return {
            "ok": False,
            "text": _fallback_reply(final_status),
            "ai_status": final_status,
            "error": last_error,
        }

    except Exception as e:
        final_status = _classify_error(e)
        console_log(
            "ERROR",
            "GEMINI",
            "Gemini Service phát sinh ngoại lệ",
            status=final_status,
            model=model,
            error=e,
        )
        return {
            "ok": False,
            "text": _fallback_reply(final_status),
            "ai_status": final_status,
            "error": str(e),
        }


# Chức năng: Gửi câu hỏi tới Gemini khi router cần AI phụ trợ.
# Vai trò: Giữ tương thích với các module cũ chỉ nhận nội dung văn bản.
def ask_gemini(question, context=""):
    result = ask_gemini_status(
        question,
        context=context,
    )
    return result.get("text") or _fallback_reply(
        result.get("ai_status", "AI_FALLBACK")
    )
