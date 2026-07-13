"""
sheet_api.py - BOT CAP 3.1
Nhiệm vụ: kết nối Google Sheets, đọc dữ liệu chuẩn hóa, ghi log và lưu session.
Nguyên tắc: Google Sheets là nguồn dữ liệu nghiệp vụ duy nhất; file này không chứa hardcode nghiệp vụ.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials

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
_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
CACHE_TTL_SECONDS = int(os.getenv("SHEET_CACHE_TTL_SECONDS", "30"))


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
    # Chức năng: Khởi tạo client gspread.
    # Vai trò: Tái sử dụng kết nối Google Sheets trong toàn bộ BOT.
    global _client
    if _client is None:
        creds = _credentials_from_env()
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet():
    # Chức năng: Mở Google Spreadsheet theo GOOGLE_SHEET_ID.
    # Vai trò: Cung cấp workbook trung tâm dữ liệu cho BOT.
    global _spreadsheet
    if _spreadsheet is None:
        if not GOOGLE_SHEET_ID:
            raise ValueError("Thiếu GOOGLE_SHEET_ID")
        _spreadsheet = get_client().open_by_key(GOOGLE_SHEET_ID)
    return _spreadsheet


def get_worksheet(sheet_name: str):
    # Chức năng: Lấy worksheet theo tên sheet.
    # Vai trò: Cung cấp dữ liệu từng bảng cho BOT theo tên được cấu hình trong Google Sheets.
    return get_spreadsheet().worksheet(sheet_name)


def ensure_worksheet(sheet_name: str, headers: Optional[List[str]] = None, rows: int = 1000, cols: int = 20):
    # Chức năng: Lấy worksheet, nếu chưa có thì tạo mới.
    # Vai trò: Bảo đảm các sheet hệ thống/log/session luôn tồn tại khi BOT cần ghi dữ liệu.
    ss = get_spreadsheet()
    try:
        ws = ss.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=sheet_name, rows=rows, cols=cols)
        if headers:
            ws.append_row(headers)
    return ws


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
    if sheet_name:
        _cache.pop(sheet_name, None)
    else:
        _cache.clear()

# Chức năng: Tổng hợp trạng thái cache dữ liệu Google Sheets hiện có.
# Vai trò: Giúp health check xác định BOT còn dữ liệu dự phòng khi Google Sheets tạm thời lỗi.
def get_sheet_cache_status() -> Dict[str, Any]:
    now = time.time()
    sheet_count = 0
    data_sheet_count = 0
    oldest_age_seconds = 0

    for cached_at, cached_rows in _cache.values():
        sheet_count += 1
        cache_age = max(0, int(now - cached_at))
        oldest_age_seconds = max(oldest_age_seconds, cache_age)

        if cached_rows:
            data_sheet_count += 1

    return {
        "available": sheet_count > 0,
        "has_data": data_sheet_count > 0,
        "sheet_count": sheet_count,
        "data_sheet_count": data_sheet_count,
        "oldest_age_seconds": oldest_age_seconds,
        "ttl_seconds": CACHE_TTL_SECONDS,
    }


# Chức năng: Đọc dữ liệu một sheet thành danh sách dict đã chuẩn hóa.
# Vai trò: Trả danh sách rỗng khi không có dữ liệu và phát sinh SheetReadError khi Google Sheets bị lỗi.
def read_sheet(
    sheet_name: str,
    use_cache: bool = True,
) -> List[Dict[str, str]]:
    sheet_name = _clean_value(sheet_name)

    if not sheet_name:
        error_message = "Tên sheet trống hoặc không hợp lệ"
        print(f"[SHEET READ ERROR] {error_message}")
        raise SheetReadError(error_message)

    now = time.time()
    cached_rows: List[Dict[str, str]] = []
    cached_at = 0.0

    if sheet_name in _cache:
        cached_at, cached_rows = _cache[sheet_name]

        if use_cache and now - cached_at <= CACHE_TTL_SECONDS:
            return [dict(row) for row in cached_rows]

    try:
        ws = get_worksheet(sheet_name)
        records = ws.get_all_records(default_blank="")
        rows: List[Dict[str, str]] = []

        for row in records:
            cleaned = _clean_row(row)

            if any(str(value).strip() for value in cleaned.values()):
                rows.append(cleaned)

        _cache[sheet_name] = (now, rows)

        if not rows:
            print(
                f"[SHEET EMPTY] {sheet_name}: "
                "đọc thành công nhưng không có dữ liệu"
            )

        return [dict(row) for row in rows]

    except gspread.WorksheetNotFound as e:
        print(f"[SHEET READ ERROR] {sheet_name}: không tìm thấy worksheet")

        if use_cache and cached_rows:
            cache_age = int(now - cached_at)
            print(
                f"[SHEET CACHE FALLBACK] {sheet_name}: "
                f"dùng cache cũ {cache_age} giây"
            )
            return [dict(row) for row in cached_rows]

        raise SheetReadError(
            f"Không tìm thấy worksheet: {sheet_name}"
        ) from e

    except Exception as e:
        print(
            f"[SHEET READ ERROR] {sheet_name}: "
            f"{type(e).__name__}: {e}"
        )

        if use_cache and cached_rows:
            cache_age = int(now - cached_at)
            print(
                f"[SHEET CACHE FALLBACK] {sheet_name}: "
                f"dùng cache cũ {cache_age} giây"
            )
            return [dict(row) for row in cached_rows]

        raise SheetReadError(
            f"Không thể đọc sheet {sheet_name}: "
            f"{type(e).__name__}: {e}"
        ) from e


# Chức năng: Kiểm tra trạng thái hoạt động của một dòng dữ liệu.
# Vai trò: Giúp BOT chỉ sử dụng dữ liệu đang bật trong Google Sheets.
def _is_active(row: Dict[str, Any]) -> bool:
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

    if not status:
        return True

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

    return status not in inactive_values


# Chức năng: Đọc các dòng đang hoạt động trong một sheet.
# Vai trò: Lọc dữ liệu hợp lệ và giữ nguyên lỗi Google Sheets để tầng xử lý phía trên nhận biết.
def _read_active(sheet_name: str) -> List[Dict[str, str]]:
    return [
        row
        for row in read_sheet(sheet_name)
        if _is_active(row)
    ]


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

    for row in read_sheet(sheet_name):
        if not _is_active(row):
            continue

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
        print(f"[SETTING UPDATE ERROR] {key}: {e}")
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
    # Chức năng: Ghi một lượt hội thoại vào sheet LICH_SU_CHAT.
    # Vai trò: Phục vụ kiểm tra chất lượng trả lời, truy vết nguồn dữ liệu và cải tiến BOT.
    try:
        ws = ensure_log_sheet()
        ws.append_row([
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
        clear_cache(SHEET_LICH_SU_CHAT)
        return True

    except Exception as e:
        print(f"[LOG CHAT ERROR] {e}")
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
    # Chức năng: Đọc ngữ cảnh hội thoại của một người dùng từ sheet BOT_SESSION.
    # Vai trò: Giúp BOT hiểu các câu hỏi nối tiếp trong cùng phiên chat.
    user_id = _clean_value(user_id)
    if not user_id:
        return {}

    try:
        rows = read_sheet(SHEET_SESSION, use_cache=False)
        for row in rows:
            if _clean_value(row.get("USER_ID")) == user_id:
                raw = _clean_value(row.get("CONTEXT_JSON"))
                if not raw:
                    return {}
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        return {}
                    updated_at = _clean_value(row.get("UPDATED_AT") or row.get("UPDATED_TIME"))
                    if updated_at and not data.get("updated_at"):
                        data["updated_at"] = updated_at
                    return data
                except Exception:
                    return {}
        return {}

    except Exception as e:
        print(f"[SESSION READ ERROR] {user_id}: {e}")
        return {}


def save_session(user_id: str, context: Dict[str, Any], updated_at: str) -> bool:
    # Chức năng: Lưu hoặc cập nhật ngữ cảnh hội thoại của một người dùng.
    # Vai trò: Duy trì bộ nhớ phiên chat để BOT trả lời theo ngữ cảnh.
    user_id = _clean_value(user_id)
    if not user_id:
        return False

    try:
        ws = ensure_session_sheet()
        values = ws.get_all_values()

        if not values:
            ws.append_row(["USER_ID", "CONTEXT_JSON", "UPDATED_AT"])
            values = ws.get_all_values()

        context = context or {}
        context_json = json.dumps(context, ensure_ascii=False)
        row_values = [
            user_id,
            context_json,
            _clean_value(context.get("last_route") or context.get("route")),
            _clean_value(context.get("sheet")),
            _clean_value(context.get("procedure_id") or context.get("record_id") or context.get("row_id")),
            _clean_value(context.get("topic") or context.get("last_menu")),
            _clean_value(context.get("procedure_name") or context.get("last_procedure")),
            _clean_value(context.get("page")),
            _clean_value(updated_at),
        ]

        for idx, row in enumerate(values[1:], start=2):
            current_user_id = _clean_value(row[0] if len(row) > 0 else "")
            if current_user_id == user_id:
                ws.update(f"A{idx}:I{idx}", [row_values])
                clear_cache(SHEET_SESSION)
                return True

        ws.append_row(row_values)
        clear_cache(SHEET_SESSION)
        return True

    except Exception as e:
        print(f"[SESSION SAVE ERROR] {user_id}: {e}")
        return False


# Chức năng: Kiểm tra kết nối, sheet bắt buộc, cột lõi và tham chiếu dữ liệu trong Google Sheets.
# Vai trò: Phát hiện sớm lỗi cấu trúc trước khi BOT đọc dữ liệu, định tuyến và trả lời người dân.
def sheet_health() -> Dict[str, Any]:
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
