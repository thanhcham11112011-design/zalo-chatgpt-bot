import os
import time
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from services.console_logger import console_log
from services.sheet_api import log_chat, log_unknown, read_setting_system


_debug_settings_lock = Lock()
_debug_settings_cache: Dict[str, str] = {}
_debug_settings_loaded_at = 0.0
DEBUG_SETTINGS_CACHE_SECONDS = max(
    int(os.getenv("DEBUG_SETTINGS_CACHE_SECONDS", "60")),
    1,
)


# Chức năng: Đọc và cache nhóm cấu hình log kỹ thuật từ SETTING_SYSTEM.
# Vai trò: Tránh gọi Google Sheets lặp lại mỗi lần kiểm tra DEBUG.
def _runtime_log_settings() -> Dict[str, str]:
    global _debug_settings_cache
    global _debug_settings_loaded_at

    now = time.monotonic()

    with _debug_settings_lock:
        if (
            _debug_settings_loaded_at
            and now - _debug_settings_loaded_at
            < DEBUG_SETTINGS_CACHE_SECONDS
        ):
            return dict(_debug_settings_cache)

        try:
            settings = read_setting_system() or {}
            _debug_settings_cache = {
                str(key or "").strip().upper(): str(value or "").strip()
                for key, value in settings.items()
            }
            _debug_settings_loaded_at = now
        except Exception as e:
            console_log(
                "ERROR",
                "LOGGER",
                "Không đọc được cấu hình log từ SETTING_SYSTEM",
                error=e,
            )

        return dict(_debug_settings_cache)


# Chức năng: Kiểm tra một nhóm DEBUG có đang được bật trong SETTING_SYSTEM hay không.
# Vai trò: Cho phép bật/tắt log kiểm thử từ Google Sheets mà không cần sửa code.
def _debug_enabled(group=""):
    settings = _runtime_log_settings()
    debug_mode = str(
        settings.get("DEBUG_MODE") or "OFF"
    ).strip().upper()

    if debug_mode != "ON":
        return False

    if not group:
        return True

    key = f"DEBUG_{str(group).strip().upper()}"
    return str(
        settings.get(key) or "OFF"
    ).strip().upper() == "ON"


# Chức năng: In log DEBUG theo nhóm khi được bật trong SETTING_SYSTEM.
# Vai trò: Dùng chung cho router, search, FAQ, thủ tục, liên hệ, AI và webhook.
def debug_print(group, *values):
    if not _debug_enabled(group):
        return

    console_log(
        "DEBUG",
        group or "GENERAL",
        " | ".join(_safe_text(value) for value in values),
    )

# Chức năng: Lấy thời gian hiện tại theo định dạng chuẩn ghi log.
# Vai trò: Thống nhất mốc thời gian Việt Nam cho lịch sử hội thoại, unknown log và lỗi hệ thống.
def current_time() -> str:
    settings = _runtime_log_settings()
    timezone_name = str(
        settings.get("TIMEZONE")
        or os.getenv("BOT_TIMEZONE")
        or "Asia/Ho_Chi_Minh"
    ).strip()

    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(timezone_name)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            pass

    return datetime.now(
        timezone(timedelta(hours=7))
    ).strftime("%Y-%m-%d %H:%M:%S")


# Chức năng: Chuyển dữ liệu bất kỳ thành chuỗi an toàn để ghi log.
# Vai trò: Tránh lỗi khi log nhận dữ liệu rỗng, dict, list hoặc object.
def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list, tuple, set)):
        return str(value)

    return str(value)


# Chức năng: Ghép ghi chú kỹ thuật thành một chuỗi thống nhất.
# Vai trò: Lưu trạng thái AI, fallback, unknown và lỗi mà không phụ thuộc thêm cột mới.
def _build_note(
    note: str = "",
    ai_status: str = "",
    ai_model: str = "",
    ai_called: Any = "",
    elapsed_ms: Any = "",
    error_code: str = "",
    error_message: str = "",
) -> str:
    parts = []

    if note:
        parts.append(f"NOTE={_safe_text(note)}")
    if ai_status:
        parts.append(f"AI_STATUS={_safe_text(ai_status)}")
    if ai_model:
        parts.append(f"AI_MODEL={_safe_text(ai_model)}")
    if ai_called != "":
        parts.append(f"AI_CALLED={_safe_text(ai_called)}")
    if elapsed_ms != "":
        parts.append(f"ELAPSED_MS={_safe_text(elapsed_ms)}")
    if error_code:
        parts.append(f"ERROR_CODE={_safe_text(error_code)}")
    if error_message:
        parts.append(f"ERROR={_safe_text(error_message)}")

    return " | ".join(parts)


# Chức năng: Ghi một lượt hội thoại vào Google Sheets.
# Vai trò: Là đầu mối log thống nhất cho app.py và các module xử lý.
def write_log(
    user_id: str,
    user_message: str,
    bot_reply: str,
    source: str = "BOT",
    route: str = "",
    score: Any = "",
    sheet: str = "",
    row_id: str = "",
    note: str = "",
    ai_status: str = "",
    ai_model: str = "",
    ai_called: Any = "",
    elapsed_ms: Any = "",
    error_code: str = "",
    error_message: str = "",
) -> bool:
    try:
        final_note = _build_note(
            note=note,
            ai_status=ai_status,
            ai_model=ai_model,
            ai_called=ai_called,
            elapsed_ms=elapsed_ms,
            error_code=error_code,
            error_message=error_message,
        )

        return log_chat(
            thoi_gian=current_time(),
            user_id=_safe_text(user_id),
            user_message=_safe_text(user_message),
            bot_reply=_safe_text(bot_reply),
            source=_safe_text(source or "BOT"),
            route=_safe_text(route),
            score=_safe_text(score),
            sheet=_safe_text(sheet),
            row_id=_safe_text(row_id),
            note=final_note,
        )

    except Exception as e:
        console_log("ERROR", "LOGGER", "Ghi lịch sử chat thất bại", error=e)
        return False


# Chức năng: Ghi lỗi xử lý vào lịch sử chat.
# Vai trò: Hỗ trợ truy vết lỗi khi webhook, router, AI hoặc Zalo phát sinh ngoại lệ.
def log_error(
    user_id: str = "",
    user_message: str = "",
    error_message: str = "",
    route: str = "ERROR",
    note: str = "",
    error_code: str = "",
) -> bool:
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=error_message,
        source="ERROR",
        route=route,
        score="",
        sheet="",
        row_id="",
        note=note,
        error_code=error_code,
        error_message=error_message,
    )


# Chức năng: Ghi câu hỏi chưa có dữ liệu phù hợp vào Google Sheets.
# Vai trò: Tạo nguồn kiểm thử để bổ sung dữ liệu, FAQ hoặc từ khóa trong Sheet.
def write_unknown_log(
    user_id: str,
    user_message: str,
    route: str = "UNKNOWN",
    note: str = "NO_MATCH",
    score: Any = "",
    sheet: str = "",
    row_id: str = "",
    ai_called: Any = "",
    ai_status: str = "",
) -> bool:
    try:
        final_note = _build_note(
            note=note,
            ai_called=ai_called,
            ai_status=ai_status,
        )

        return log_unknown(
            thoi_gian=current_time(),
            user_id=_safe_text(user_id),
            user_message=_safe_text(user_message),
            route=_safe_text(route),
            note=final_note,
        )

    except Exception as e:
        console_log("ERROR", "LOGGER", "Ghi unknown log thất bại", error=e)
        return False


# Chức năng: Ghi sự kiện AI vào lịch sử chat.
# Vai trò: Theo dõi trạng thái AI Optional, quota, timeout, fallback và lỗi API.
def log_ai_event(
    user_id: str = "",
    user_message: str = "",
    ai_status: str = "",
    ai_model: str = "",
    bot_reply: str = "",
    route: str = "AI_EVENT",
    elapsed_ms: Any = "",
    error_code: str = "",
    error_message: str = "",
    note: str = "",
) -> bool:
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=bot_reply,
        source="AI",
        route=route,
        score="",
        sheet="",
        row_id="",
        note=note,
        ai_status=ai_status,
        ai_model=ai_model,
        ai_called=True,
        elapsed_ms=elapsed_ms,
        error_code=error_code,
        error_message=error_message,
    )


# Chức năng: Ghi sự kiện AI fallback vào lịch sử chat.
# Vai trò: Phân biệt trường hợp Gemini không khả dụng nhưng BOT vẫn hoạt động theo Google Sheets.
def log_ai_fallback(
    user_id: str = "",
    user_message: str = "",
    ai_status: str = "",
    fallback_message: str = "",
    route: str = "AI_FALLBACK",
    ai_model: str = "",
    note: str = "",
) -> bool:
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=fallback_message,
        source="AI_FALLBACK",
        route=route,
        score="",
        sheet="",
        row_id="",
        note=note,
        ai_status=ai_status,
        ai_model=ai_model,
        ai_called=True,
    )


# Chức năng: In log kỹ thuật theo giao diện tương thích với app.py.
# Vai trò: Dùng cùng cơ chế DEBUG trong SETTING_SYSTEM và định dạng console thống nhất.
def debug_log(title: str, data: Optional[Any] = None) -> None:
    if isinstance(data, dict):
        debug_print(
            title,
            *[
                f"{key}={_safe_text(value)}"
                for key, value in data.items()
            ],
        )
        return

    debug_print(title, data if data is not None else "")
