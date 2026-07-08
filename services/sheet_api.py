"""
sheet_api.py - BOT CAP 3.1
Nhiệm vụ: kết nối Google Sheets, đọc dữ liệu chuẩn hóa, ghi log và lưu session.
Nguyên tắc: Google Sheets là nguồn dữ liệu nghiệp vụ duy nhất; file này không chứa hardcode nghiệp vụ.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from services.logger import debug_print
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_CREDENTIALS_JSON,
    SHEET_MENU,
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

def _clean_value(value: Any) -> str:
    # Chức năng: Chuẩn hóa giá trị đọc từ Google Sheets.
    # Vai trò: Bảo đảm dữ liệu đầu vào ổn định trước khi BOT xử lý.
    if value is None:
        return ""

    text = str(value).strip()

    if text.startswith("'"):
        text = text[1:].strip()

    if text.endswith(".0") and text.replace(".0", "", 1).isdigit():
        text = text[:-2]

    if text.isdigit() and len(text) in [9, 10]:
        text = "0" + text

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

def clear_cache(sheet_name: Optional[str] = None):
    # Chức năng: Xóa cache dữ liệu sheet.
    # Vai trò: Giúp BOT đọc lại dữ liệu mới sau khi Google Sheets được cập nhật.
    if sheet_name:
        _cache.pop(sheet_name, None)
    else:
        _cache.clear()


def read_sheet(sheet_name: str, use_cache: bool = True) -> List[Dict[str, str]]:
    # Chức năng: Đọc dữ liệu một sheet thành danh sách dict đã chuẩn hóa.
    # Vai trò: Là hàm đọc dữ liệu trung tâm cho toàn bộ BOT CAP 3.1.
    sheet_name = _clean_value(sheet_name)
    if not sheet_name:
        return []

    now = time.time()

    if use_cache and sheet_name in _cache:
        cached_at, rows = _cache[sheet_name]
        if now - cached_at <= CACHE_TTL_SECONDS:
            return [dict(r) for r in rows]

    try:
        ws = get_worksheet(sheet_name)
        records = ws.get_all_records(default_blank="")
        rows: List[Dict[str, str]] = []

        for row in records:
            cleaned = _clean_row(row)
            if any(str(v).strip() for v in cleaned.values()):
                rows.append(cleaned)
    debug_print(
        "SHEET",
        f"SHEET={sheet_name}",
        f"ROWS={len(rows)}"
    )
        _cache[sheet_name] = (now, rows)
        return [dict(r) for r in rows]

    except gspread.WorksheetNotFound:
        print(f"[SHEET WARNING] Không tìm thấy sheet: {sheet_name}")
        return []

    except Exception as e:
        print(f"[SHEET READ ERROR] {sheet_name}: {e}")
        return []


def _is_active(row: Dict[str, Any]) -> bool:
    # Chức năng: Kiểm tra trạng thái hoạt động của một dòng dữ liệu.
    # Vai trò: Giúp BOT chỉ sử dụng dữ liệu đang bật trong Google Sheets.
    status = _get_first(row, ["TRANG_THAI", "TRẠNG_THÁI", "STATUS", "ACTIVE", "HIEN_THI", "HIỂN_THỊ"]).lower()

    if not status:
        return True

    inactive_values = {"off", "inactive", "false", "0", "no", "khong", "không", "ngung", "ngừng", "dung", "dừng"}
    return status not in inactive_values


def _read_active(sheet_name: str) -> List[Dict[str, str]]:
    # Chức năng: Đọc các dòng đang hoạt động trong một sheet.
    # Vai trò: Là lớp lọc dữ liệu hợp lệ trước khi BOT tìm kiếm, định tuyến và trả lời.
    return [row for row in read_sheet(sheet_name) if _is_active(row)]


# =========================
# PUBLIC READ FUNCTIONS
# =========================

def read_menu() -> List[Dict[str, str]]:
    # Chức năng: Đọc sheet MENU.
    # Vai trò: Cung cấp dữ liệu định tuyến chức năng cho BOT.
    return _read_active(SHEET_MENU)


def read_lien_he() -> List[Dict[str, str]]:
    # Chức năng: Đọc sheet TRA_CUU_LIEN_HE.
    # Vai trò: Cung cấp dữ liệu liên hệ cán bộ, bộ phận, trực ban cho BOT.
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


# =========================
# DEBUG / HEALTH
# =========================

def sheet_health() -> Dict[str, Any]:
    # Chức năng: Kiểm tra tình trạng kết nối và sự tồn tại của các sheet bắt buộc.
    # Vai trò: Hỗ trợ kiểm tra nhanh hệ thống BOT trước và sau khi deploy.
    result = {
        "ok": False,
        "spreadsheet_id": GOOGLE_SHEET_ID,
        "sheets": {},
        "total_required": 0,
        "total_missing": 0,
        "missing": [],
        "error": "",
    }

    try:
        ss = get_spreadsheet()
        existing = {ws.title for ws in ss.worksheets()}
        check_sheets = [
            SHEET_MENU,
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
            *read_thu_tuc_sheet_names(),
        ]

        for name in check_sheets:
            exists = name in existing
            result["sheets"][name] = exists
            if not exists:
                result["missing"].append(name)

        result["total_required"] = len(check_sheets)
        result["total_missing"] = len(result["missing"])
        result["ok"] = result["total_missing"] == 0

    except Exception as e:
        result["error"] = str(e)

    return result
