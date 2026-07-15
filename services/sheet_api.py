"""
sheet_api.py - BOT CAP 3.1
Nhiệm vụ: kết nối Google Sheets, đọc dữ liệu chuẩn hóa, ghi log và lưu session.
Nguyên tắc: Google Sheets là nguồn dữ liệu nghiệp vụ duy nhất; file này không chứa hardcode nghiệp vụ.
"""

import json
from copy import deepcopy
import os
import time
from datetime import date, datetime, timedelta, timezone
from threading import Lock, RLock
from typing import Any, Dict, List, Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from services.console_logger import console_log

from config import (
    GOOGLE_SHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_CREDENTIALS_JSON,
    SHEET_MENU,
    SHEET_FILTER_BAD_WORD,
    SHEET_SETTING_SYSTEM,
    SHEET_SETTING_AI,
    SHEET_SETTING_CHAT,
    SHEET_PROMPT,
    SHEET_THONGTIN,
    SHEET_TRA_CUU_LIEN_HE,
    SHEET_FAQ,
    SHEET_LICH_SU_CHAT,
    SHEET_SESSION,
)

try:
    from config import SHEET_DATA_DICTIONARY, SHEET_BOT_31_SCHEMA
except Exception:
    SHEET_DATA_DICTIONARY = "DATA_DICTIONARY"
    SHEET_BOT_31_SCHEMA = "BOT_31_SCHEMA"


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_spreadsheet = None
_worksheet_cache: Dict[str, Any] = {}
_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_sheet_locks: Dict[str, Lock] = {}
_google_read_retry_after = 0.0

_client_lock = Lock()
_spreadsheet_lock = Lock()
_worksheet_lock = RLock()
_cache_lock = RLock()
_sheet_locks_lock = Lock()
_log_write_lock = Lock()
_session_write_lock = Lock()
_sheet_health_lock = Lock()
_sheet_health_cache_at = 0.0
_sheet_health_cache_data: Dict[str, Any] = {}

CACHE_TTL_SECONDS = int(
    os.getenv("SHEET_CACHE_TTL_SECONDS", "300")
)

CACHE_MAX_STALE_SECONDS = max(
    CACHE_TTL_SECONDS,
    int(os.getenv("SHEET_CACHE_MAX_STALE_SECONDS", "1800")),
)

SHEET_429_COOLDOWN_SECONDS = max(
    30,
    int(os.getenv("SHEET_429_COOLDOWN_SECONDS", "60")),
)

SHEET_HEALTH_CACHE_SECONDS = max(
    60,
    int(os.getenv("SHEET_HEALTH_CACHE_SECONDS", "300")),
)

VALID_FROM_KEYS = [
    "HIEU_LUC_TU",
    "HIỆU_LỰC_TỪ",
    "NGAY_HIEU_LUC",
    "NGÀY_HIỆU_LỰC",
    "TU_NGAY",
    "TỪ_NGÀY",
    "VALID_FROM",
    "START_DATE",
]

VALID_TO_KEYS = [
    "HIEU_LUC_DEN",
    "HIỆU_LỰC_ĐẾN",
    "NGAY_HET_HAN",
    "NGÀY_HẾT_HẠN",
    "DEN_NGAY",
    "ĐẾN_NGÀY",
    "VALID_TO",
    "END_DATE",
    "EXPIRES_AT",
]

_data_validity_lock = Lock()
_data_validity_status: Dict[str, Dict[str, Any]] = {}
_data_validity_warning_signatures: Dict[str, str] = {}


# =========================
# CLEAN DATA
# =========================

# Chức năng: Chuẩn hóa giá trị đọc từ Google Sheets.
# Vai trò: Làm sạch dữ liệu chung mà không tự thay đổi số điện thoại, mã hoặc ID.
def _clean_value(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if text.startswith("'"):
        text = text[1:].strip()

    if text.endswith(".0") and text.replace(".0", "", 1).isdigit():
        text = text[:-2]

    return text

def _clean_key(key: Any) -> str:
    # Chức năng: Chuẩn hóa tên cột đọc từ Google Sheets.
    # Vai trò: Giúp BOT nhận đúng cột dữ liệu, tránh lỗi do thừa khoảng trắng hoặc sai chữ hoa/thường.
    return str(key or "").strip().upper()


def _clean_row(row: Dict[str, Any]) -> Dict[str, str]:
    # Chức năng: Chuẩn hóa toàn bộ một dòng dữ liệu.
    # Vai trò: Chuyển dữ liệu sheet thành dict sạch để các module khác sử dụng.
    cleaned: Dict[str, str] = {}
    for k, v in (row or {}).items():
        key = _clean_key(k)
        if key:
            cleaned[key] = _clean_value(v)
    return cleaned


def _get_first(row: Dict[str, Any], keys: List[str], default: str = "") -> str:
    # Chức năng: Lấy giá trị đầu tiên có dữ liệu theo danh sách tên cột.
    # Vai trò: Hỗ trợ tương thích nhiều biến thể tên cột trong Google Sheets.
    for key in keys:
        value = _clean_value(row.get(_clean_key(key)))
        if value:
            return value
    return default


# =========================
# GOOGLE CONNECTION
# =========================

def _credentials_from_env() -> Credentials:
    # Chức năng: Lấy thông tin xác thực Google API từ biến môi trường hoặc file credentials.
    # Vai trò: Kết nối BOT với Google Sheets.
    if GOOGLE_CREDENTIALS_JSON:
        raw = GOOGLE_CREDENTIALS_JSON.strip()
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            info = json.loads(raw.replace("\\n", "\n"))

        if "private_key" in info:
            info["private_key"] = str(info["private_key"]).replace("\\n", "\n")

        return Credentials.from_service_account_info(info, scopes=SCOPES)

    credentials_path = GOOGLE_CREDENTIALS_FILE or "credentials.json"
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Không tìm thấy file credentials: {credentials_path}. "
            "Hãy cấu hình GOOGLE_CREDENTIALS_JSON hoặc GOOGLE_CREDENTIALS_FILE."
        )

    return Credentials.from_service_account_file(credentials_path, scopes=SCOPES)


def get_client():
    # Chức năng: Khởi tạo client gspread an toàn khi nhiều luồng cùng truy cập.
    # Vai trò: Tái sử dụng một kết nối Google Sheets trong toàn bộ tiến trình BOT.
    global _client

    if _client is not None:
        return _client

    with _client_lock:
        if _client is None:
            creds = _credentials_from_env()
            _client = gspread.authorize(creds)

    return _client


def get_spreadsheet():
    # Chức năng: Mở Google Spreadsheet một lần và dùng lại trong toàn bộ tiến trình.
    # Vai trò: Tránh nhiều luồng cùng tạo kết nối workbook sau khi Render khởi động.
    global _spreadsheet

    if _spreadsheet is not None:
        return _spreadsheet

    with _spreadsheet_lock:
        if _spreadsheet is None:
            if not GOOGLE_SHEET_ID:
                raise ValueError("Thiếu GOOGLE_SHEET_ID")
            _spreadsheet = get_client().open_by_key(
                GOOGLE_SHEET_ID
            )

    return _spreadsheet


def _load_worksheet_cache() -> None:
    # Chức năng: Nạp danh sách worksheet vào bộ nhớ bằng một lần đọc metadata.
    # Vai trò: Tránh gọi Spreadsheet.worksheet riêng cho từng sheet và từng lượt ghi.
    if _worksheet_cache:
        return

    worksheets = get_spreadsheet().worksheets()

    for worksheet in worksheets:
        _worksheet_cache[worksheet.title] = worksheet


def get_worksheet(sheet_name: str):
    # Chức năng: Lấy worksheet từ cache metadata theo tên sheet.
    # Vai trò: Giảm lượt đọc metadata Google Sheets trong các luồng đọc và ghi.
    normalized_name = _clean_value(sheet_name)

    if not normalized_name:
        raise gspread.WorksheetNotFound(
            "Tên worksheet trống"
        )

    with _worksheet_lock:
        _load_worksheet_cache()
        worksheet = _worksheet_cache.get(normalized_name)

        if worksheet is not None:
            return worksheet

        _worksheet_cache.clear()
        _load_worksheet_cache()
        worksheet = _worksheet_cache.get(normalized_name)

        if worksheet is None:
            raise gspread.WorksheetNotFound(
                normalized_name
            )

        return worksheet


def ensure_worksheet(
    sheet_name: str,
    headers: Optional[List[str]] = None,
    rows: int = 1000,
    cols: int = 20,
):
    # Chức năng: Lấy worksheet từ cache, nếu chưa có thì tạo mới một lần.
    # Vai trò: Bảo đảm sheet hệ thống tồn tại mà không đọc metadata ở mỗi lượt ghi.
    normalized_name = _clean_value(sheet_name)

    if not normalized_name:
        raise ValueError("Tên worksheet trống")

    with _worksheet_lock:
        _load_worksheet_cache()
        worksheet = _worksheet_cache.get(normalized_name)

        if worksheet is not None:
            return worksheet

        worksheet = get_spreadsheet().add_worksheet(
            title=normalized_name,
            rows=rows,
            cols=cols,
        )

        if headers:
            worksheet.append_row(headers)

        _worksheet_cache[normalized_name] = worksheet
        return worksheet


# =========================
# READ HELPERS + CACHE
# =========================

# Chức năng: Đại diện lỗi kỹ thuật khi không thể đọc dữ liệu Google Sheets.
# Vai trò: Phân biệt lỗi Google Sheets với trường hợp Sheet đọc thành công nhưng không có dữ liệu.
class SheetReadError(RuntimeError):
    pass


# Chức năng: Xóa cache dữ liệu sheet.
# Vai trò: Giúp BOT đọc lại dữ liệu mới sau khi Google Sheets được cập nhật.
def clear_cache(sheet_name: Optional[str] = None):
    with _cache_lock:
        if sheet_name:
            _cache.pop(sheet_name, None)
        else:
            _cache.clear()


def _get_sheet_lock(sheet_name: str) -> Lock:
    # Chức năng: Lấy khóa đọc riêng cho từng sheet.
    # Vai trò: Ngăn nhiều thread cùng nạp một sheet khi cache trống hoặc hết hạn.
    with _sheet_locks_lock:
        lock = _sheet_locks.get(sheet_name)

        if lock is None:
            lock = Lock()
            _sheet_locks[sheet_name] = lock

        return lock


def _is_quota_error(error: Exception) -> bool:
    # Chức năng: Nhận diện lỗi vượt quota Google Sheets API.
    # Vai trò: Kích hoạt thời gian tạm dừng đọc để tránh các webhook tiếp tục gọi dồn dập.
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    error_text = str(error or "").lower()

    return (
        status_code == 429
        or "[429]" in error_text
        or "quota exceeded" in error_text
        or "too many requests" in error_text
    )


# Chức năng: Kiểm tra cache cũ có còn được phép dùng làm dữ liệu dự phòng hay không.
# Vai trò: Ngăn BOT sử dụng dữ liệu Google Sheets quá thời hạn cho phép.
def _get_cache_fallback(
    sheet_name: str,
    cached_at: float,
    cached_rows: List[Dict[str, str]],
    now: float,
    use_cache: bool,
) -> Optional[List[Dict[str, str]]]:
    if not use_cache or not cached_rows or not cached_at:
        return None

    cache_age = max(0, int(now - cached_at))

    if cache_age <= CACHE_MAX_STALE_SECONDS:
        console_log(
            "WARNING",
            "SHEET_CACHE",
            "Dùng cache cũ do Google Sheets không khả dụng",
            sheet=sheet_name,
            cache_age_seconds=cache_age,
        )
        return [dict(row) for row in cached_rows]

    console_log(
        "WARNING",
        "SHEET_CACHE",
        "Cache đã hết thời hạn dự phòng",
        sheet=sheet_name,
        cache_age_seconds=cache_age,
        max_stale_seconds=CACHE_MAX_STALE_SECONDS,
    )

    with _cache_lock:
        _cache.pop(sheet_name, None)

    return None


# Chức năng: Tổng hợp trạng thái cache dữ liệu Google Sheets hiện có.
# Vai trò: Giúp health check nhận biết cache còn hợp lệ, cache dự phòng và cache đã hết hạn.
def get_sheet_cache_status() -> Dict[str, Any]:
    now = time.time()
    sheet_count = 0
    data_sheet_count = 0
    fresh_sheet_count = 0
    fallback_sheet_count = 0
    expired_sheet_count = 0
    oldest_age_seconds = 0

    with _cache_lock:
        cache_snapshot = [
            (
                cached_at,
                [dict(row) for row in cached_rows],
            )
            for cached_at, cached_rows in _cache.values()
        ]
        retry_after = _google_read_retry_after

    for cached_at, cached_rows in cache_snapshot:
        sheet_count += 1
        cache_age = max(0, int(now - cached_at))
        oldest_age_seconds = max(
            oldest_age_seconds,
            cache_age,
        )

        if cache_age <= CACHE_TTL_SECONDS:
            fresh_sheet_count += 1
        elif cache_age <= CACHE_MAX_STALE_SECONDS:
            fallback_sheet_count += 1
        else:
            expired_sheet_count += 1

        if (
            cached_rows
            and cache_age <= CACHE_MAX_STALE_SECONDS
        ):
            data_sheet_count += 1

    valid_sheet_count = (
        fresh_sheet_count
        + fallback_sheet_count
    )

    return {
        "available": valid_sheet_count > 0,
        "has_data": data_sheet_count > 0,
        "sheet_count": sheet_count,
        "valid_sheet_count": valid_sheet_count,
        "data_sheet_count": data_sheet_count,
        "fresh_sheet_count": fresh_sheet_count,
        "fallback_sheet_count": fallback_sheet_count,
        "expired_sheet_count": expired_sheet_count,
        "oldest_age_seconds": oldest_age_seconds,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "max_stale_seconds": CACHE_MAX_STALE_SECONDS,
        "quota_cooldown_active": retry_after > now,
        "quota_retry_after_seconds": max(
            0,
            int(retry_after - now),
        ),
    }


# Chức năng: Đọc một sheet với cache, khóa chống đọc trùng và tạm dừng khi gặp lỗi 429.
# Vai trò: Giảm lượt gọi Google Sheets trong môi trường có nhiều người dùng đồng thời.
def read_sheet(
    sheet_name: str,
    use_cache: bool = True,
) -> List[Dict[str, str]]:
    global _google_read_retry_after

    sheet_name = _clean_value(sheet_name)

    if not sheet_name:
        error_message = "Tên sheet trống hoặc không hợp lệ"
        console_log("ERROR", "SHEET_READ", error_message)
        raise SheetReadError(error_message)

    sheet_lock = _get_sheet_lock(sheet_name)

    with sheet_lock:
        now = time.time()

        with _cache_lock:
            cached_at, cached_rows = _cache.get(
                sheet_name,
                (0.0, []),
            )
            cached_rows = [
                dict(row)
                for row in cached_rows
            ]
            retry_after = _google_read_retry_after

        cache_age = max(
            0,
            int(now - cached_at),
        ) if cached_at else 0

        if (
            use_cache
            and cached_at
            and cache_age <= CACHE_TTL_SECONDS
        ):
            return cached_rows

        if retry_after > now:
            fallback_rows = _get_cache_fallback(
                sheet_name=sheet_name,
                cached_at=cached_at,
                cached_rows=cached_rows,
                now=now,
                use_cache=use_cache,
            )

            if fallback_rows is not None:
                return fallback_rows

            raise SheetReadError(
                f"Google Sheets đang tạm dừng đọc sau lỗi 429; "
                f"thử lại sau {max(1, int(retry_after - now))} giây"
            )

        try:
            worksheet = get_worksheet(sheet_name)
            records = worksheet.get_all_records(
                default_blank="",
                numericise_ignore=["all"],
            )
            rows: List[Dict[str, str]] = []

            for row in records:
                cleaned = _clean_row(row)

                if any(
                    str(value).strip()
                    for value in cleaned.values()
                ):
                    rows.append(cleaned)

            cached_time = time.time()

            with _cache_lock:
                _cache[sheet_name] = (
                    cached_time,
                    rows,
                )

            if not rows:
                console_log(
                    "INFO",
                    "SHEET_READ",
                    "Đọc thành công nhưng sheet không có dữ liệu",
                    sheet=sheet_name,
                )

            return [
                dict(row)
                for row in rows
            ]

        except gspread.WorksheetNotFound as error:
            console_log(
                "ERROR",
                "SHEET_READ",
                "Không tìm thấy worksheet",
                sheet=sheet_name,
            )

            fallback_rows = _get_cache_fallback(
                sheet_name=sheet_name,
                cached_at=cached_at,
                cached_rows=cached_rows,
                now=now,
                use_cache=use_cache,
            )

            if fallback_rows is not None:
                return fallback_rows

            raise SheetReadError(
                f"Không tìm thấy worksheet: {sheet_name}"
            ) from error

        except Exception as error:
            if _is_quota_error(error):
                with _cache_lock:
                    _google_read_retry_after = (
                        time.time()
                        + SHEET_429_COOLDOWN_SECONDS
                    )

            console_log(
                "ERROR",
                "SHEET_READ",
                "Không thể đọc Google Sheets",
                sheet=sheet_name,
                error_type=type(error).__name__,
                error=error,
            )

            fallback_rows = _get_cache_fallback(
                sheet_name=sheet_name,
                cached_at=cached_at,
                cached_rows=cached_rows,
                now=now,
                use_cache=use_cache,
            )

            if fallback_rows is not None:
                return fallback_rows

            raise SheetReadError(
                f"Không thể đọc sheet {sheet_name}: "
                f"{type(error).__name__}: {error}"
            ) from error


# Chức năng: Lấy ngày hiện tại theo múi giờ kỹ thuật của hệ thống.
# Vai trò: So sánh ngày hiệu lực dữ liệu thống nhất với múi giờ vận hành BOT.
def _local_today() -> date:
    timezone_name = str(
        os.getenv("BOT_TIMEZONE")
        or os.getenv("TZ")
        or "Asia/Ho_Chi_Minh"
    ).strip()

    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(timezone_name)).date()
        except Exception:
            pass

    return datetime.now(timezone(timedelta(hours=7))).date()


# Chức năng: Chuyển giá trị ngày trong Google Sheets thành ngày chuẩn.
# Vai trò: Hỗ trợ các định dạng ngày phổ biến mà không phụ thuộc định dạng hiển thị của một sheet.
def _parse_sheet_date(value: Any) -> Tuple[Optional[date], bool]:
    text = _clean_value(value)

    if not text:
        return None, True

    iso_text = text.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(iso_text).date(), True
    except Exception:
        pass

    formats = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    )

    for date_format in formats:
        try:
            return datetime.strptime(text, date_format).date(), True
        except ValueError:
            continue

    return None, False


# Chức năng: Xác định trạng thái sử dụng của một dòng theo trạng thái và thời hạn dữ liệu.
# Vai trò: Loại dữ liệu tắt, chưa có hiệu lực, đã hết hạn hoặc có ngày không hợp lệ trước khi định tuyến.
def _row_validity_state(
    row: Dict[str, Any],
    today: Optional[date] = None,
) -> str:
    status = _get_first(
        row,
        [
            "TRANG_THAI",
            "TRẠNG_THÁI",
            "STATUS",
            "ACTIVE",
            "HIEN_THI",
            "HIỂN_THỊ",
        ],
    ).lower()

    inactive_values = {
        "off",
        "inactive",
        "false",
        "0",
        "no",
        "khong",
        "không",
        "ngung",
        "ngừng",
        "dung",
        "dừng",
    }

    if status in inactive_values:
        return "inactive_status"

    valid_from_raw = _get_first(row, VALID_FROM_KEYS)
    valid_to_raw = _get_first(row, VALID_TO_KEYS)
    valid_from, valid_from_ok = _parse_sheet_date(valid_from_raw)
    valid_to, valid_to_ok = _parse_sheet_date(valid_to_raw)

    if not valid_from_ok or not valid_to_ok:
        return "invalid_date"

    if valid_from and valid_to and valid_from > valid_to:
        return "invalid_range"

    current_date = today or _local_today()

    if valid_from and current_date < valid_from:
        return "not_started"

    if valid_to and current_date > valid_to:
        return "expired"

    return "active"


# Chức năng: Lưu thống kê thời hạn mới nhất của từng sheet vào bộ nhớ tiến trình.
# Vai trò: Cung cấp trạng thái quản trị qua health check mà không phát sinh lượt đọc Google Sheets riêng.
def _save_data_validity_status(
    sheet_name: str,
    counts: Dict[str, int],
    invalid_samples: List[str],
) -> None:
    normalized_sheet = _clean_value(sheet_name) or "UNKNOWN"
    snapshot = {
        "total_rows": sum(counts.values()),
        "active_rows": counts.get("active", 0),
        "inactive_status_rows": counts.get("inactive_status", 0),
        "not_started_rows": counts.get("not_started", 0),
        "expired_rows": counts.get("expired", 0),
        "invalid_date_rows": (
            counts.get("invalid_date", 0)
            + counts.get("invalid_range", 0)
        ),
        "checked_date": _local_today().isoformat(),
        "invalid_samples": invalid_samples[:5],
    }

    with _data_validity_lock:
        _data_validity_status[normalized_sheet] = snapshot
        signature = "|".join(invalid_samples[:20])
        previous_signature = _data_validity_warning_signatures.get(
            normalized_sheet,
            "",
        )
        _data_validity_warning_signatures[normalized_sheet] = signature

    if signature and signature != previous_signature:
        console_log(
            "WARNING",
            "DATA_VALIDITY",
            "Phát hiện dữ liệu có ngày hiệu lực không hợp lệ",
            sheet=normalized_sheet,
            invalid_count=snapshot["invalid_date_rows"],
            samples=invalid_samples[:5],
        )


# Chức năng: Lọc danh sách dòng theo trạng thái và thời hạn hiệu lực.
# Vai trò: Áp dụng một quy tắc thời hạn chung cho MENU, FAQ, liên hệ, thủ tục và cấu hình Sheet.
def _filter_active_rows(
    sheet_name: str,
    rows: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    today = _local_today()
    counts = {
        "active": 0,
        "inactive_status": 0,
        "not_started": 0,
        "expired": 0,
        "invalid_date": 0,
        "invalid_range": 0,
    }
    active_rows: List[Dict[str, str]] = []
    invalid_samples: List[str] = []

    for row_number, row in enumerate(rows, start=2):
        state = _row_validity_state(row, today=today)
        counts[state] = counts.get(state, 0) + 1

        if state == "active":
            active_rows.append(row)
            continue

        if state not in {"invalid_date", "invalid_range"}:
            continue

        row_id = _get_first(
            row,
            [
                "ID",
                "MA",
                "MÃ",
                "MA_THU_TUC",
                "MÃ_THỦ_TỤC",
                "KEY",
                "TEN_THU_TUC",
                "TÊN_THỦ_TỤC",
                "TEN_CO_QUAN",
                "TÊN_CƠ_QUAN",
            ],
            default=f"ROW_{row_number}",
        )
        invalid_samples.append(
            f"{row_id}:{state}"
        )

    _save_data_validity_status(
        sheet_name=sheet_name,
        counts=counts,
        invalid_samples=invalid_samples,
    )
    return active_rows


# Chức năng: Kiểm tra trạng thái hoạt động và thời hạn của một dòng dữ liệu.
# Vai trò: Giữ tương thích với các vùng kiểm tra cấu trúc đang gọi trực tiếp hàm này.
def _is_active(row: Dict[str, Any]) -> bool:
    return _row_validity_state(row) == "active"


# Chức năng: Đọc các dòng đang hoạt động và còn thời hạn trong một sheet.
# Vai trò: Lọc dữ liệu hợp lệ và giữ nguyên lỗi Google Sheets để tầng xử lý phía trên nhận biết.
def _read_active(
    sheet_name: str,
) -> List[Dict[str, str]]:
    return _filter_active_rows(
        sheet_name=sheet_name,
        rows=read_sheet(sheet_name),
    )


# Chức năng: Tổng hợp trạng thái thời hạn dữ liệu đã được kiểm tra trong tiến trình hiện tại.
# Vai trò: Cung cấp số liệu quản trị cho health check mà không đọc lại Google Sheets.
def get_data_validity_status() -> Dict[str, Any]:
    with _data_validity_lock:
        sheets = {
            sheet_name: dict(status)
            for sheet_name, status in _data_validity_status.items()
        }

    totals = {
        "total_rows": 0,
        "active_rows": 0,
        "inactive_status_rows": 0,
        "not_started_rows": 0,
        "expired_rows": 0,
        "invalid_date_rows": 0,
    }

    for status in sheets.values():
        for key in totals:
            totals[key] += int(status.get(key, 0) or 0)

    return {
        "ok": totals["invalid_date_rows"] == 0,
        "tracked_sheet_count": len(sheets),
        **totals,
        "sheets": sheets,
    }

# =========================
# PUBLIC READ FUNCTIONS
# =========================

# Chức năng: Đọc các quy tắc ngăn chặn từ ngữ thiếu văn hóa từ Google Sheets.
# Vai trò: Cung cấp dữ liệu kiểm duyệt cho Search Engine mà không hardcode từ ngữ trong Python.
def read_filter_bad_word() -> List[Dict[str, str]]:
    return _read_active(SHEET_FILTER_BAD_WORD)


# Chức năng: Đọc sheet MENU.
# Vai trò: Cung cấp dữ liệu định tuyến chức năng cho BOT.
def read_menu() -> List[Dict[str, str]]:
    return _read_active(SHEET_MENU)


# Chức năng: Đọc sheet TRA_CUU_LIEN_HE.
# Vai trò: Cung cấp dữ liệu liên hệ cán bộ, bộ phận, trực ban cho BOT.
def read_lien_he() -> List[Dict[str, str]]:
    return _read_active(SHEET_TRA_CUU_LIEN_HE)


def read_faq() -> List[Dict[str, str]]:
    # Chức năng: Đọc sheet FAQ.
    # Vai trò: Cung cấp dữ liệu hỏi đáp nhanh cho BOT.
    return _read_active(SHEET_FAQ)


def read_thu_tuc_sheet(sheet_name: str) -> List[Dict[str, str]]:
    # Chức năng: Đọc một sheet thủ tục theo tên sheet lấy từ dữ liệu MENU.
    # Vai trò: Gắn nguồn sheet vào từng thủ tục để BOT truy vết dữ liệu.
    rows = _read_active(sheet_name)
    for row in rows:
        row["_SHEET"] = sheet_name
    return rows


def read_thu_tuc_sheet_names() -> List[str]:
    # Chức năng: Lấy danh sách sheet thủ tục từ MENU.SHEET_DU_LIEU.
    # Vai trò: Loại bỏ danh sách hardcode THU_TUC_* trong Python.
    names: List[str] = []
    seen = set()

    for row in read_menu():
        sheet_name = _get_first(row, ["SHEET_DU_LIEU", "SHEET DỮ LIỆU", "SHEET", "TEN_SHEET", "TÊN_SHEET"])
        if not sheet_name:
            continue

        sheet_name_upper = sheet_name.upper()
        if not sheet_name_upper.startswith("THU_TUC_"):
            continue

        if sheet_name_upper not in seen:
            seen.add(sheet_name_upper)
            names.append(sheet_name)

    return names


def read_all_thu_tuc() -> List[Dict[str, str]]:
    # Chức năng: Đọc toàn bộ sheet thủ tục được khai báo trong MENU.
    # Vai trò: Tạo nguồn dữ liệu thủ tục tổng hợp mà không hardcode lĩnh vực nghiệp vụ trong Python.
    all_rows: List[Dict[str, str]] = []

    for sheet_name in read_thu_tuc_sheet_names():
        all_rows.extend(read_thu_tuc_sheet(sheet_name))

    return all_rows


def read_thongtin() -> Dict[str, str]:
    # Chức năng: Đọc sheet THONGTIN dạng key-value.
    # Vai trò: Cung cấp thông tin đơn vị cho BOT từ Google Sheets.
    return _key_value_sheet(SHEET_THONGTIN)


def read_setting_system() -> Dict[str, str]:
    # Chức năng: Đọc sheet SETTING_SYSTEM dạng key-value.
    # Vai trò: Cung cấp cấu hình hệ thống cho BOT từ Google Sheets.
    return _key_value_sheet(SHEET_SETTING_SYSTEM)


def read_setting_ai() -> Dict[str, str]:
    # Chức năng: Đọc sheet SETTING_AI dạng key-value.
    # Vai trò: Cung cấp cấu hình AI cho BOT từ Google Sheets.
    return _key_value_sheet(SHEET_SETTING_AI)


def read_setting_chat() -> Dict[str, str]:
    # Chức năng: Đọc sheet SETTING_CHAT dạng key-value.
    # Vai trò: Cung cấp cấu hình nội dung hội thoại cho BOT từ Google Sheets.
    return _key_value_sheet(SHEET_SETTING_CHAT)


def read_prompt() -> Dict[str, str]:
    # Chức năng: Đọc sheet PROMPT dạng key-value.
    # Vai trò: Cung cấp prompt điều khiển AI cho BOT từ Google Sheets.
    return _key_value_sheet(SHEET_PROMPT)


def read_data_dictionary() -> List[Dict[str, str]]:
    # Chức năng: Đọc sheet DATA_DICTIONARY.
    # Vai trò: Cung cấp tài liệu mô tả cấu trúc dữ liệu BOT CAP 3.1.
    return _read_active(SHEET_DATA_DICTIONARY)


def read_bot_31_schema() -> List[Dict[str, str]]:
    # Chức năng: Đọc sheet BOT_31_SCHEMA.
    # Vai trò: Cung cấp quy tắc khóa chuẩn kiến trúc BOT CAP 3.1.
    return _read_active(SHEET_BOT_31_SCHEMA)


# =========================
# KEY/VALUE SETTINGS
# =========================

def _key_value_sheet(sheet_name: str) -> Dict[str, str]:
    # Chức năng: Đọc sheet dạng KEY/VALUE thành dict cấu hình.
    # Vai trò: Cung cấp cấu hình hệ thống, AI, chat, prompt và thông tin đơn vị cho BOT.
    data: Dict[str, str] = {}
    active_rows = _filter_active_rows(
        sheet_name=sheet_name,
        rows=read_sheet(sheet_name),
    )

    for row in active_rows:
        key = _get_first(row, ["KEY", "MA", "MÃ", "TEN", "TÊN", "ID", "PROMPT_NAME", "SETTING_KEY"])
        value = _get_first(row, ["VALUE", "GIA_TRI", "GIÁ_TRỊ", "NOI_DUNG", "NỘI_DUNG", "MO_TA", "MÔ_TẢ", "PROMPT", "TEXT"])

        if key:
            data[key] = value

    return data


def update_setting_system(key: str, value: Any) -> bool:
    # Chức năng: Cập nhật hoặc tạo mới một KEY trong sheet SETTING_SYSTEM.
    # Vai trò: Cho phép BOT lưu cấu hình hệ thống động như token hoặc tham số vận hành.
    try:
        ws = ensure_worksheet(
            SHEET_SETTING_SYSTEM,
            headers=["KEY", "VALUE", "DESCRIPTION", "STATUS"],
            rows=200,
            cols=10,
        )

        values = ws.get_all_values()
        if not values:
            ws.append_row(["KEY", "VALUE", "DESCRIPTION", "STATUS"])
            values = ws.get_all_values()

        key = _clean_value(key)
        value = _clean_value(value)

        for idx, row in enumerate(values[1:], start=2):
            current_key = _clean_value(row[0] if len(row) > 0 else "")
            if current_key == key:
                ws.update(f"B{idx}", [[value]])
                clear_cache(SHEET_SETTING_SYSTEM)
                return True

        ws.append_row([key, value, "", "ON"])
        clear_cache(SHEET_SETTING_SYSTEM)
        return True

    except Exception as e:
        console_log("ERROR", "SHEET_WRITE", "Cập nhật SETTING_SYSTEM thất bại", key=key, error=e)
        return False


# =========================
# LOG CHAT
# =========================

def ensure_log_sheet():
    # Chức năng: Bảo đảm sheet LICH_SU_CHAT tồn tại.
    # Vai trò: Chuẩn bị nơi lưu lịch sử hội thoại của BOT.
    return ensure_worksheet(
        SHEET_LICH_SU_CHAT,
        headers=[
            "THOI_GIAN",
            "USER_ID",
            "TIN_NHAN",
            "BOT_REPLY",
            "SOURCE",
            "ROUTE",
            "SCORE",
            "SHEET",
            "ROW_ID",
            "NOTE",
        ],
        rows=5000,
        cols=15,
    )


def log_chat(
    thoi_gian: str,
    user_id: str,
    user_message: str,
    bot_reply: str,
    source: str = "BOT",
    route: str = "",
    score: Any = "",
    sheet: str = "",
    row_id: str = "",
    note: str = "",
) -> bool:
    # Chức năng: Ghi tuần tự một lượt hội thoại vào sheet LICH_SU_CHAT.
    # Vai trò: Tránh nhiều thread cùng mở worksheet và ghi chồng trong môi trường đa người dùng.
    try:
        with _log_write_lock:
            worksheet = ensure_log_sheet()
            worksheet.append_row([
                _clean_value(thoi_gian),
                _clean_value(user_id),
                _clean_value(user_message),
                _clean_value(bot_reply),
                _clean_value(source),
                _clean_value(route),
                _clean_value(score),
                _clean_value(sheet),
                _clean_value(row_id),
                _clean_value(note),
            ])

        return True

    except Exception as error:
        console_log(
            "ERROR",
            "SHEET_LOG",
            "Ghi LICH_SU_CHAT thất bại",
            error=error,
        )
        return False


def log_unknown(
    thoi_gian: str,
    user_id: str,
    user_message: str,
    route: str = "UNKNOWN",
    note: str = "NO_MATCH",
) -> bool:
    # Chức năng: Ghi nhận câu hỏi chưa tìm thấy dữ liệu phù hợp.
    # Vai trò: Tạo nguồn dữ liệu để bổ sung FAQ, từ khóa hoặc thủ tục trong Google Sheets.
    return log_chat(
        thoi_gian=thoi_gian,
        user_id=user_id,
        user_message=user_message,
        bot_reply="",
        source="UNKNOWN",
        route=route,
        score="",
        sheet="",
        row_id="",
        note=note,
    )


# =========================
# SESSION SHEET
# =========================

def ensure_session_sheet():
    # Chức năng: Bảo đảm sheet BOT_SESSION tồn tại.
    # Vai trò: Chuẩn bị nơi lưu ngữ cảnh hội thoại theo từng người dùng.
    return ensure_worksheet(
        SHEET_SESSION,
        headers=[
            "USER_ID",
            "CONTEXT_JSON",
            "LAST_ROUTE",
            "LAST_SHEET",
            "LAST_RECORD_ID",
            "LAST_MENU",
            "LAST_PROCEDURE",
            "PAGE",
            "UPDATED_AT",
        ],
        rows=2000,
        cols=12,
    )


def read_session(user_id: str) -> Dict[str, Any]:
    # Chức năng: Đọc ngữ cảnh người dùng từ cache BOT_SESSION trước khi gọi Google Sheets.
    # Vai trò: Tránh buộc đọc toàn bộ BOT_SESSION ở mỗi lượt nhắn hoặc cache miss của session RAM.
    user_id = _clean_value(user_id)

    if not user_id:
        return {}

    try:
        rows = read_sheet(
            SHEET_SESSION,
            use_cache=True,
        )

        for row in rows:
            if _clean_value(
                row.get("USER_ID")
            ) != user_id:
                continue

            raw = _clean_value(
                row.get("CONTEXT_JSON")
            )

            if not raw:
                return {}

            try:
                data = json.loads(raw)

                if not isinstance(data, dict):
                    return {}

                updated_at = _clean_value(
                    row.get("UPDATED_AT")
                    or row.get("UPDATED_TIME")
                )

                if (
                    updated_at
                    and not data.get("updated_at")
                ):
                    data["updated_at"] = updated_at

                return data

            except Exception:
                return {}

        return {}

    except Exception as error:
        console_log(
            "ERROR",
            "SHEET_SESSION",
            "Đọc BOT_SESSION thất bại",
            user_id=user_id,
            error=error,
        )
        return {}


def save_session(
    user_id: str,
    context: Dict[str, Any],
    updated_at: str,
) -> bool:
    # Chức năng: Lưu session và cập nhật ngay cache BOT_SESSION trong bộ nhớ.
    # Vai trò: Không đọc get_all_values và không xóa cache sau mỗi lần cập nhật ngữ cảnh.
    user_id = _clean_value(user_id)

    if not user_id:
        return False

    try:
        with _session_write_lock:
            worksheet = ensure_session_sheet()
            rows = read_sheet(
                SHEET_SESSION,
                use_cache=True,
            )
            context = context or {}
            context_json = json.dumps(
                context,
                ensure_ascii=False,
            )
            cache_row = {
                "USER_ID": user_id,
                "CONTEXT_JSON": context_json,
                "LAST_ROUTE": _clean_value(
                    context.get("last_route")
                    or context.get("route")
                ),
                "LAST_SHEET": _clean_value(
                    context.get("sheet")
                ),
                "LAST_RECORD_ID": _clean_value(
                    context.get("procedure_id")
                    or context.get("record_id")
                    or context.get("row_id")
                ),
                "LAST_MENU": _clean_value(
                    context.get("topic")
                    or context.get("last_menu")
                ),
                "LAST_PROCEDURE": _clean_value(
                    context.get("procedure_name")
                    or context.get("last_procedure")
                ),
                "PAGE": _clean_value(
                    context.get("page")
                ),
                "UPDATED_AT": _clean_value(
                    updated_at
                ),
            }
            row_values = [
                cache_row["USER_ID"],
                cache_row["CONTEXT_JSON"],
                cache_row["LAST_ROUTE"],
                cache_row["LAST_SHEET"],
                cache_row["LAST_RECORD_ID"],
                cache_row["LAST_MENU"],
                cache_row["LAST_PROCEDURE"],
                cache_row["PAGE"],
                cache_row["UPDATED_AT"],
            ]
            row_number = 0

            for index, row in enumerate(
                rows,
                start=2,
            ):
                if _clean_value(
                    row.get("USER_ID")
                ) == user_id:
                    row_number = index
                    break

            if row_number:
                worksheet.update(
                    f"A{row_number}:I{row_number}",
                    [row_values],
                )
                rows[row_number - 2] = cache_row
            else:
                worksheet.append_row(row_values)
                rows.append(cache_row)

            with _cache_lock:
                _cache[SHEET_SESSION] = (
                    time.time(),
                    [
                        dict(row)
                        for row in rows
                    ],
                )

        return True

    except Exception as error:
        console_log(
            "ERROR",
            "SHEET_SESSION",
            "Lưu BOT_SESSION thất bại",
            user_id=user_id,
            error=error,
        )
        return False


# Chức năng: Kiểm tra kết nối, sheet bắt buộc, cột lõi và tham chiếu dữ liệu trong Google Sheets.
# Vai trò: Phát hiện sớm lỗi cấu trúc trước khi BOT đọc dữ liệu, định tuyến và trả lời người dân.
def _build_sheet_health() -> Dict[str, Any]:
    result = {
        "ok": False,
        "spreadsheet_id": GOOGLE_SHEET_ID,
        "sheets": {},
        "schema": {},
        "procedure_sheets": [],
        "missing": [],
        "menu_references_missing": [],
        "duplicate_menu_ids": [],
        "menu_rows_missing_sheet": [],
        "total_required": 0,
        "total_missing": 0,
        "errors": [],
        "error": "",
    }

    try:
        ss = get_spreadsheet()
        worksheets = {ws.title: ws for ws in ss.worksheets()}
        existing = set(worksheets.keys())

        procedure_sheets: List[str] = []
        menu_references: List[str] = []

        core_sheets = [
            SHEET_MENU,
            SHEET_FILTER_BAD_WORD,
            SHEET_SETTING_SYSTEM,
            SHEET_SETTING_AI,
            SHEET_SETTING_CHAT,
            SHEET_PROMPT,
            SHEET_THONGTIN,
            SHEET_TRA_CUU_LIEN_HE,
            SHEET_FAQ,
            SHEET_LICH_SU_CHAT,
            SHEET_SESSION,
            SHEET_DATA_DICTIONARY,
            SHEET_BOT_31_SCHEMA,
        ]

        if SHEET_MENU in worksheets:
            menu_values = worksheets[SHEET_MENU].get_all_values()
            menu_headers = [
                _clean_key(value)
                for value in (menu_values[0] if menu_values else [])
            ]

            required_menu_headers = [
                ("ID", {"ID", "MENU_ID"}),
                (
                    "TEN_CHUC_NANG",
                    {
                        "TEN_CHUC_NANG",
                        "TÊN_CHỨC_NĂNG",
                        "TEN CHUC NANG",
                        "TÊN CHỨC NĂNG",
                    },
                ),
                ("MO_TA", {"MO_TA", "MÔ_TẢ", "MO TA", "MÔ TẢ"}),
                ("TU_KHOA", {"TU_KHOA", "TỪ_KHÓA", "TU KHOA", "TỪ KHÓA"}),
                (
                    "SHEET_DU_LIEU",
                    {
                        "SHEET_DU_LIEU",
                        "SHEET DỮ LIỆU",
                        "SHEET",
                        "TEN_SHEET",
                        "TÊN_SHEET",
                    },
                ),
                (
                    "TRANG_THAI",
                    {
                        "TRANG_THAI",
                        "TRẠNG_THÁI",
                        "STATUS",
                        "ACTIVE",
                    },
                ),
            ]

            missing_headers = [
                label
                for label, aliases in required_menu_headers
                if not any(alias in menu_headers for alias in aliases)
            ]

            result["schema"][SHEET_MENU] = {
                "headers_ok": not missing_headers,
                "missing_headers": missing_headers,
            }

            menu_ids: Dict[str, List[int]] = {}

            for row_number, raw_row in enumerate(menu_values[1:], start=2):
                row = {
                    menu_headers[index]: _clean_value(
                        raw_row[index] if index < len(raw_row) else ""
                    )
                    for index in range(len(menu_headers))
                    if menu_headers[index]
                }

                if not any(row.values()) or not _is_active(row):
                    continue

                menu_id = _get_first(row, ["ID", "MENU_ID"])
                if menu_id:
                    menu_ids.setdefault(menu_id, []).append(row_number)

                sheet_name = _get_first(
                    row,
                    [
                        "SHEET_DU_LIEU",
                        "SHEET DỮ LIỆU",
                        "SHEET",
                        "TEN_SHEET",
                        "TÊN_SHEET",
                    ],
                )

                if not sheet_name:
                    result["menu_rows_missing_sheet"].append({
                        "row": row_number,
                        "id": menu_id,
                        "name": _get_first(
                            row,
                            [
                                "TEN_CHUC_NANG",
                                "TÊN_CHỨC_NĂNG",
                                "TEN CHUC NANG",
                                "TÊN CHỨC NĂNG",
                            ],
                        ),
                    })
                    continue

                if sheet_name not in menu_references:
                    menu_references.append(sheet_name)

                if (
                    sheet_name.upper().startswith("THU_TUC_")
                    and sheet_name not in procedure_sheets
                ):
                    procedure_sheets.append(sheet_name)

            result["duplicate_menu_ids"] = [
                {
                    "id": menu_id,
                    "rows": row_numbers,
                }
                for menu_id, row_numbers in menu_ids.items()
                if len(row_numbers) > 1
            ]

        required_sheets: List[str] = []

        for sheet_name in [*core_sheets, *procedure_sheets]:
            sheet_name = _clean_value(sheet_name)

            if sheet_name and sheet_name not in required_sheets:
                required_sheets.append(sheet_name)

        for sheet_name in required_sheets:
            exists = sheet_name in existing
            result["sheets"][sheet_name] = exists

            if not exists:
                result["missing"].append(sheet_name)

        result["procedure_sheets"] = procedure_sheets
        result["menu_references_missing"] = [
            sheet_name
            for sheet_name in menu_references
            if sheet_name not in existing
        ]

        sheet_requirements = {
            SHEET_TRA_CUU_LIEN_HE: [
                ("BO_PHAN", {"BO_PHAN", "BỘ_PHẬN", "BO PHAN", "BỘ PHẬN"}),
                ("TDP", {"TDP", "TO_DAN_PHO", "TỔ_DÂN_PHỐ", "TỔ DÂN PHỐ"}),
                ("TU_KHOA", {"TU_KHOA", "TỪ_KHÓA", "TU KHOA", "TỪ KHÓA"}),
                (
                    "TEN_CO_QUAN",
                    {
                        "TEN_CO_QUAN",
                        "TÊN_CƠ_QUAN",
                        "TEN CO QUAN",
                        "TÊN CƠ QUAN",
                    },
                ),
                (
                    "CHUC_NANG",
                    {
                        "CHUC_NANG",
                        "CHỨC_NĂNG",
                        "CHUC NANG",
                        "CHỨC NĂNG",
                    },
                ),
                (
                    "SO_DIEN_THOAI",
                    {
                        "SO_DIEN_THOAI",
                        "SỐ_ĐIỆN_THOẠI",
                        "SO DIEN THOAI",
                        "SỐ ĐIỆN THOẠI",
                    },
                ),
                ("GOOGLE_MAP", {"GOOGLE_MAP", "GOOGLE MAP", "MAP"}),
                ("GHI_CHU", {"GHI_CHU", "GHI_CHÚ", "GHI CHU", "GHI CHÚ"}),
                (
                    "TRANG_THAI",
                    {
                        "TRANG_THAI",
                        "TRẠNG_THÁI",
                        "STATUS",
                        "ACTIVE",
                    },
                ),
                ("UU_TIEN", {"UU_TIEN", "ƯU_TIÊN", "UU TIEN", "ƯU TIÊN"}),
            ],
            SHEET_FAQ: [
                ("CAU_HOI", {"CAU_HOI", "CÂU_HỎI", "CAU HOI", "CÂU HỎI"}),
                (
                    "CAC_CACH_HOI",
                    {
                        "CAC_CACH_HOI",
                        "CÁC_CÁCH_HỎI",
                        "CAC CACH HOI",
                        "CÁC CÁCH HỎI",
                    },
                ),
                ("TU_KHOA", {"TU_KHOA", "TỪ_KHÓA", "TU KHOA", "TỪ KHÓA"}),
                ("TRA_LOI", {"TRA_LOI", "TRẢ_LỜI", "TRA LOI", "TRẢ LỜI"}),
                (
                    "RELATED_ID",
                    {
                        "RELATED_ID",
                        "RELATED",
                        "MA_THU_TUC",
                        "MÃ_THỦ_TỤC",
                    },
                ),
                ("NGU_CANH", {"NGU_CANH", "NGỮ_CẢNH", "NGU CANH", "NGỮ CẢNH"}),
                (
                    "TRANG_THAI",
                    {
                        "TRANG_THAI",
                        "TRẠNG_THÁI",
                        "STATUS",
                        "ACTIVE",
                    },
                ),
            ],
        }

        for sheet_name, requirements in sheet_requirements.items():
            if sheet_name not in worksheets:
                continue

            headers = {
                _clean_key(value)
                for value in worksheets[sheet_name].row_values(1)
                if _clean_key(value)
            }

            missing_headers = [
                label
                for label, aliases in requirements
                if not any(alias in headers for alias in aliases)
            ]

            result["schema"][sheet_name] = {
                "headers_ok": not missing_headers,
                "missing_headers": missing_headers,
            }

        procedure_requirements = [
            (
                "MA_THU_TUC",
                {
                    "MA_THU_TUC",
                    "MÃ_THỦ_TỤC",
                    "MA THU TUC",
                    "MÃ THỦ TỤC",
                    "ID",
                },
            ),
            (
                "TEN_THU_TUC",
                {
                    "TEN_THU_TUC",
                    "TÊN_THỦ_TỤC",
                    "TEN THU TUC",
                    "TÊN THỦ TỤC",
                },
            ),
            ("TU_KHOA", {"TU_KHOA", "TỪ_KHÓA", "TU KHOA", "TỪ KHÓA"}),
            (
                "NOI_NOP",
                {
                    "NOI_NOP",
                    "NƠI_NỘP",
                    "NOI_THUC_HIEN",
                    "NƠI_THỰC_HIỆN",
                    "CO_QUAN_THUC_HIEN",
                    "CƠ_QUAN_THỰC_HIỆN",
                },
            ),
            (
                "DOI_TUONG",
                {
                    "DOI_TUONG",
                    "ĐỐI_TƯỢNG",
                    "DOI TUONG",
                    "ĐỐI TƯỢNG",
                    "DOI_TUONG_AP_DUNG",
                    "ĐỐI_TƯỢNG_ÁP_DỤNG",
                    "DOI TUONG AP DUNG",
                    "ĐỐI TƯỢNG ÁP DỤNG",
                },
            ),
            ("DIEU_KIEN", {"DIEU_KIEN", "ĐIỀU_KIỆN", "DIEU KIEN", "ĐIỀU KIỆN"}),
            ("HO_SO", {"HO_SO", "HỒ_SƠ", "HO SO", "HỒ SƠ"}),
            ("TRINH_TU", {"TRINH_TU", "TRÌNH_TỰ", "TRINH TU", "TRÌNH TỰ"}),
            ("THOI_HAN", {"THOI_HAN", "THỜI_HẠN", "THOI HAN", "THỜI HẠN"}),
            ("LE_PHI", {"LE_PHI", "LỆ_PHÍ", "LE PHI", "LỆ PHÍ"}),
            ("LINK_DVC", {"LINK_DVC", "LINK DVC", "DICH_VU_CONG"}),
            (
                "TRANG_THAI",
                {
                    "TRANG_THAI",
                    "TRẠNG_THÁI",
                    "STATUS",
                    "ACTIVE",
                },
            ),
        ]

        for sheet_name in procedure_sheets:
            if sheet_name not in worksheets:
                continue

            headers = {
                _clean_key(value)
                for value in worksheets[sheet_name].row_values(1)
                if _clean_key(value)
            }

            missing_headers = [
                label
                for label, aliases in procedure_requirements
                if not any(alias in headers for alias in aliases)
            ]

            result["schema"][sheet_name] = {
                "headers_ok": not missing_headers,
                "missing_headers": missing_headers,
            }

        for sheet_name, schema_result in result["schema"].items():
            if not schema_result.get("headers_ok", False):
                result["errors"].append(
                    f"{sheet_name}: thiếu cột "
                    + ", ".join(schema_result.get("missing_headers", []))
                )

        if result["duplicate_menu_ids"]:
            result["errors"].append(
                "MENU có ID trùng tại các dòng đang hoạt động"
            )

        if result["menu_rows_missing_sheet"]:
            result["errors"].append(
                "MENU có dòng đang hoạt động nhưng thiếu SHEET_DU_LIEU"
            )

        if result["menu_references_missing"]:
            result["errors"].append(
                "MENU trỏ tới sheet không tồn tại: "
                + ", ".join(result["menu_references_missing"])
            )

        result["total_required"] = len(required_sheets)
        result["total_missing"] = len(result["missing"])
        result["ok"] = (
            result["total_missing"] == 0
            and not result["errors"]
        )

    except Exception as e:
        result["error"] = str(e)
        result["errors"].append(str(e))

    return result

# Chức năng: Trả trạng thái Google Sheets từ cache và chỉ kiểm tra cấu trúc theo chu kỳ.
# Vai trò: Ngăn endpoint health tạo nhiều lượt đọc metadata và dữ liệu trong mỗi phút.
def sheet_health() -> Dict[str, Any]:
    global _sheet_health_cache_at
    global _sheet_health_cache_data

    now = time.time()

    with _sheet_health_lock:
        cache_age = max(
            0,
            int(now - _sheet_health_cache_at),
        ) if _sheet_health_cache_at else 0

        if (
            _sheet_health_cache_data
            and cache_age <= SHEET_HEALTH_CACHE_SECONDS
        ):
            return deepcopy(
                _sheet_health_cache_data
            )

        result = _build_sheet_health()
        _sheet_health_cache_at = time.time()
        _sheet_health_cache_data = deepcopy(
            result
        )
        return deepcopy(result)

