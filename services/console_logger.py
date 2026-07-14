import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


LOG_VALUE_MAX_LENGTH = max(
    int(os.getenv("LOG_VALUE_MAX_LENGTH", "2000")),
    200,
)


# Chức năng: Lấy thời gian hiện tại theo múi giờ kỹ thuật của hệ thống.
# Vai trò: Thống nhất mốc thời gian cho toàn bộ log console mà không phụ thuộc Google Sheets.
def _local_now() -> datetime:
    timezone_name = str(
        os.getenv("BOT_TIMEZONE")
        or os.getenv("TZ")
        or "Asia/Ho_Chi_Minh"
    ).strip()

    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(timezone_name))
        except Exception:
            pass

    return datetime.now(timezone(timedelta(hours=7)))


# Chức năng: Chuyển giá trị log thành chuỗi một dòng có giới hạn độ dài.
# Vai trò: Giữ log dễ đọc và tránh in dữ liệu quá lớn lên Render.
def _format_log_value(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list, tuple, set)):
        try:
            text = json.dumps(
                value,
                ensure_ascii=False,
                default=str,
                sort_keys=True,
            )
        except Exception:
            text = str(value)
    else:
        text = str(value)

    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())

    if len(text) > LOG_VALUE_MAX_LENGTH:
        return text[:LOG_VALUE_MAX_LENGTH] + "..."

    return text


# Chức năng: In một dòng log console theo cấu trúc thời gian, mức độ, nhóm và trường dữ liệu.
# Vai trò: Là đầu mối log kỹ thuật dùng chung cho app và các service, không ghi nghiệp vụ vào code.
def console_log(
    level: str,
    group: str,
    message: Any = "",
    **fields: Any,
) -> None:
    normalized_level = str(level or "INFO").strip().upper()
    normalized_group = str(group or "SYSTEM").strip().upper()
    timestamp = _local_now().isoformat(timespec="seconds")
    parts = [
        f"[{timestamp}]",
        f"[{normalized_level}]",
        f"[{normalized_group}]",
    ]

    message_text = _format_log_value(message)
    if message_text:
        parts.append(message_text)

    field_parts = []
    for key, value in fields.items():
        value_text = _format_log_value(value)
        if value_text:
            field_parts.append(
                f"{str(key or '').strip().upper()}={value_text}"
            )

    if field_parts:
        parts.append(" | ".join(field_parts))

    print(" ".join(parts), flush=True)
