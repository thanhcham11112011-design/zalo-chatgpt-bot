"""
sheet_api.py - BOT CAP Phu Lien V2.2
Nhiem vu: ket noi Google Sheets, doc du lieu cac sheet, ghi log va luu session.
Luu y quan trong: file nay KHONG import router_service/search_engine/gemini/zalo de tranh circular import.
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
    SHEET_SETTING_SYSTEM,
    SHEET_SETTING_AI,
    SHEET_SETTING_CHAT,
    SHEET_PROMPT,
    SHEET_THONGTIN,
    SHEET_TRA_CUU_LIEN_HE,
    SHEET_FAQ,
    SHEET_LICH_SU_CHAT,
    SHEET_SESSION,
    THU_TUC_SHEETS,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_spreadsheet = None
_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
CACHE_TTL_SECONDS = int(os.getenv("SHEET_CACHE_TTL_SECONDS", "30"))


# =========================
# CORE CONNECT GOOGLE SHEET
# =========================

def _clean_value(value: Any) -> str:
    """Chuan hoa gia tri doc tu Google Sheet/Excel."""
    if value is None:
        return ""
    text = str(value).strip()
    # Excel hay luu so dien thoai dang '090xxx de giu so 0 dau.
    if text.startswith("'"):
        text = text[1:].strip()
    return text


def _clean_row(row: Dict[str, Any]) -> Dict[str, str]:
    return {str(k).strip(): _clean_value(v) for k, v in (row or {}).items() if str(k).strip()}


def _credentials_from_env() -> Credentials:
    if GOOGLE_CREDENTIALS_JSON:
        raw = GOOGLE_CREDENTIALS_JSON.strip()
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            # Truong hop Render env bi escape ky tu xuong dong trong private_key
            info = json.loads(raw.replace("\\n", "\n"))
        if "private_key" in info:
            info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    credentials_path = GOOGLE_CREDENTIALS_FILE or "credentials.json"
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Khong tim thay file credentials: {credentials_path}. "
            "Hay cau hinh GOOGLE_CREDENTIALS_JSON hoac GOOGLE_CREDENTIALS_FILE."
        )
    return Credentials.from_service_account_file(credentials_path, scopes=SCOPES)


def get_client():
    global _client
    if _client is None:
        creds = _credentials_from_env()
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet():
    global _spreadsheet
    if _spreadsheet is None:
        if not GOOGLE_SHEET_ID:
            raise ValueError("Thieu GOOGLE_SHEET_ID")
        _spreadsheet = get_client().open_by_key(GOOGLE_SHEET_ID)
    return _spreadsheet


def get_worksheet(sheet_name: str):
    return get_spreadsheet().worksheet(sheet_name)


def ensure_worksheet(sheet_name: str, headers: Optional[List[str]] = None, rows: int = 1000, cols: int = 20):
    """Lay worksheet; neu chua co thi tao moi va ghi header."""
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
    if sheet_name:
        _cache.pop(sheet_name, None)
    else:
        _cache.clear()


def read_sheet(sheet_name: str, use_cache: bool = True) -> List[Dict[str, str]]:
    """Doc sheet thanh list dict. Tu dong bo qua dong rong."""
    now = time.time()
    if use_cache and sheet_name in _cache:
        cached_at, rows = _cache[sheet_name]
        if now - cached_at <= CACHE_TTL_SECONDS:
            return [dict(r) for r in rows]

    try:
        ws = get_worksheet(sheet_name)
        records = ws.get_all_records(default_blank="")
        rows = []
        for row in records:
            cleaned = _clean_row(row)
            if any(str(v).strip() for v in cleaned.values()):
                rows.append(cleaned)
        _cache[sheet_name] = (now, rows)
        return [dict(r) for r in rows]
    except gspread.WorksheetNotFound:
        print(f"[SHEET WARNING] Khong tim thay sheet: {sheet_name}")
        return []
    except Exception as e:
        print(f"[SHEET READ ERROR] {sheet_name}: {e}")
        return []


def _is_active(row: Dict[str, Any]) -> bool:
    status = _clean_value(
        row.get("TRANG_THAI")
        or row.get("TRẠNG_THÁI")
        or row.get("STATUS")
        or row.get("ACTIVE")
    ).lower()
    if status in ["off", "inactive", "false", "0", "no", "khong", "không", "ngung", "dung", "dừng"]:
        return False
    return True


def _read_active(sheet_name: str) -> List[Dict[str, str]]:
    return [row for row in read_sheet(sheet_name) if _is_active(row)]


# =========================
# PUBLIC READ FUNCTIONS
# =========================

def read_menu() -> List[Dict[str, str]]:
    return _read_active(SHEET_MENU)


def read_lien_he() -> List[Dict[str, str]]:
    return _read_active(SHEET_TRA_CUU_LIEN_HE)


def read_faq() -> List[Dict[str, str]]:
    return _read_active(SHEET_FAQ)


def read_thu_tuc_sheet(sheet_name: str) -> List[Dict[str, str]]:
    rows = _read_active(sheet_name)
    for row in rows:
        row["_SHEET"] = sheet_name
    return rows


def read_all_thu_tuc() -> List[Dict[str, str]]:
    all_rows: List[Dict[str, str]] = []
    for sheet_name in THU_TUC_SHEETS:
        all_rows.extend(read_thu_tuc_sheet(sheet_name))
    return all_rows


def read_thongtin() -> Dict[str, str]:
    return _key_value_sheet(SHEET_THONGTIN)


def read_setting_system() -> Dict[str, str]:
    return _key_value_sheet(SHEET_SETTING_SYSTEM)


def read_setting_ai() -> Dict[str, str]:
    return _key_value_sheet(SHEET_SETTING_AI)


def read_setting_chat() -> Dict[str, str]:
    return _key_value_sheet(SHEET_SETTING_CHAT)


def read_prompt() -> Dict[str, str]:
    return _key_value_sheet(SHEET_PROMPT)


# =========================
# KEY/VALUE SETTINGS
# =========================

def _key_value_sheet(sheet_name: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for row in read_sheet(sheet_name):
        if not _is_active(row):
            continue
        key = (
            row.get("KEY")
            or row.get("MA")
            or row.get("MÃ")
            or row.get("TEN")
            or row.get("TÊN")
            or row.get("ID")
        )
        value = (
            row.get("VALUE")
            or row.get("GIA_TRI")
            or row.get("GIÁ_TRỊ")
            or row.get("NOI_DUNG")
            or row.get("NỘI_DUNG")
        )
        key = _clean_value(key)
        if key:
            data[key] = _clean_value(value)
    return data


def update_setting_system(key: str, value: Any) -> bool:
    """Cap nhat/tao KEY trong SETTING_SYSTEM. Dung cho Zalo token."""
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
    return ensure_worksheet(
        SHEET_LICH_SU_CHAT,
        headers=["THOI_GIAN", "USER_ID", "TIN_NHAN", "BOT_REPLY", "SOURCE"],
        rows=5000,
        cols=10,
    )


def log_chat(thoi_gian: str, user_id: str, user_message: str, bot_reply: str, source: str = "BOT") -> bool:
    try:
        ws = ensure_log_sheet()
        ws.append_row([
            _clean_value(thoi_gian),
            _clean_value(user_id),
            _clean_value(user_message),
            _clean_value(bot_reply),
            _clean_value(source),
        ])
        clear_cache(SHEET_LICH_SU_CHAT)
        return True
    except Exception as e:
        print(f"[LOG CHAT ERROR] {e}")
        return False


# =========================
# SESSION SHEET
# =========================

def ensure_session_sheet():
    return ensure_worksheet(
        SHEET_SESSION,
        headers=["USER_ID", "CONTEXT_JSON", "UPDATED_AT"],
        rows=2000,
        cols=5,
    )


# =========================
# DEBUG / HEALTH
# =========================

def sheet_health() -> Dict[str, Any]:
    result = {"ok": False, "spreadsheet_id": GOOGLE_SHEET_ID, "sheets": {}, "error": ""}
    try:
        ss = get_spreadsheet()
        existing = {ws.title for ws in ss.worksheets()}
        check_sheets = [
            SHEET_MENU,
            SHEET_TRA_CUU_LIEN_HE,
            SHEET_FAQ,
            SHEET_LICH_SU_CHAT,
            SHEET_SESSION,
            *THU_TUC_SHEETS,
        ]
        for name in check_sheets:
            result["sheets"][name] = name in existing
        result["ok"] = True
    except Exception as e:
        result["error"] = str(e)
    return result
