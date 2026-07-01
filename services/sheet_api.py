import os
import json
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_CREDENTIALS_JSON,
    ALL_SHEETS,
    THU_TUC_SHEETS,
    SHEET_SESSION,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client_cache = None
_spreadsheet_cache = None
_sheet_cache = {}


def _build_credentials():
    credentials_json = (GOOGLE_CREDENTIALS_JSON or os.getenv("GOOGLE_CREDENTIALS_JSON", "")).strip()
    if credentials_json:
        return Credentials.from_service_account_info(json.loads(credentials_json), scopes=SCOPES)
    return Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)


def get_client():
    global _client_cache
    if _client_cache:
        return _client_cache
    _client_cache = gspread.authorize(_build_credentials())
    return _client_cache


def get_spreadsheet():
    global _spreadsheet_cache
    if _spreadsheet_cache:
        return _spreadsheet_cache
    _spreadsheet_cache = get_client().open_by_key(GOOGLE_SHEET_ID)
    return _spreadsheet_cache


def get_worksheet(sheet_name):
    key = str(sheet_name).strip()
    if key in _sheet_cache:
        return _sheet_cache[key]
    ws = get_spreadsheet().worksheet(key)
    _sheet_cache[key] = ws
    return ws


def ensure_worksheet(sheet_name, header=None):
    ss = get_spreadsheet()
    try:
        ws = ss.worksheet(sheet_name)
    except Exception:
        ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(header or []), 5))
        if header:
            ws.append_row(header)
    _sheet_cache[sheet_name] = ws
    return ws


def read_sheet(sheet_name):
    try:
        return get_worksheet(sheet_name).get_all_records()
    except Exception as e:
        print(f"[SHEET ERROR] Không đọc được sheet {sheet_name}: {e}")
        return []


def is_on(row):
    status = row.get("TRANG_THAI") or row.get("STATUS") or row.get("TRẠNG_THÁI") or "ON"
    return str(status).strip().upper() in ("ON", "ACTIVE", "HOẠT ĐỘNG", "HOAT DONG", "1", "TRUE", "")


def read_active_rows(sheet_name):
    return [row for row in read_sheet(sheet_name) if is_on(row)]


def read_menu():
    return read_active_rows("MENU")


def read_settings(sheet_name):
    data = {}
    for row in read_active_rows(sheet_name):
        key = str(row.get("KEY", "")).strip()
        if key:
            data[key] = row.get("VALUE", "")
    return data


def read_setting_system():
    return read_settings("SETTING_SYSTEM")


def read_setting_ai():
    return read_settings("SETTING_AI")


def read_setting_chat():
    return read_settings("SETTING_CHAT")


def read_prompts():
    data = {}
    for row in read_active_rows("PROMPT"):
        key = str(row.get("PROMPT_NAME", "")).strip()
        if key:
            data[key] = str(row.get("NOI_DUNG", "")).strip()
    return data


def read_thongtin():
    return read_settings("THONGTIN")


def read_lien_he():
    return read_active_rows("TRA_CUU_LIEN_HE")


def read_faq():
    return read_active_rows("FAQ")


def read_thu_tuc_sheet(sheet_name):
    return read_active_rows(sheet_name)


def read_all_thu_tuc():
    data = []
    for sheet_name in THU_TUC_SHEETS:
        for row in read_active_rows(sheet_name):
            row["_SHEET"] = sheet_name
            data.append(row)
    return data


def append_row(sheet_name, values):
    try:
        get_worksheet(sheet_name).append_row(values)
        return True
    except Exception as e:
        print(f"[SHEET ERROR] Không ghi được sheet {sheet_name}: {e}")
        return False


def update_setting_system(key, value):
    try:
        ws = ensure_worksheet("SETTING_SYSTEM", ["KEY", "VALUE", "DESCRIPTION", "STATUS"])
        values = ws.get_all_values()
        if not values:
            ws.append_row(["KEY", "VALUE", "DESCRIPTION", "STATUS"])
            values = ws.get_all_values()
        header = [h.strip() for h in values[0]]
        key_col = header.index("KEY") + 1 if "KEY" in header else 1
        value_col = header.index("VALUE") + 1 if "VALUE" in header else 2
        for idx, row in enumerate(values[1:], start=2):
            if len(row) >= key_col and row[key_col - 1].strip() == key:
                ws.update_cell(idx, value_col, value)
                return True
        ws.append_row([key, value, "", "ON"])
        return True
    except Exception as e:
        print(f"[SHEET ERROR] Không cập nhật SETTING_SYSTEM {key}: {e}")
        return False


def log_chat(thoi_gian, user_id, user_message, bot_reply, source="BOT"):
    ensure_worksheet("LICH_SU_CHAT", ["THOI_GIAN", "USER_ID", "USER_MESSAGE", "BOT_REPLY", "SOURCE"])
    return append_row("LICH_SU_CHAT", [thoi_gian, user_id, user_message, bot_reply, source])


def ensure_session_sheet():
    return ensure_worksheet(SHEET_SESSION, ["USER_ID", "CONTEXT_JSON", "UPDATED_AT"])


def test_connection():
    try:
        ss = get_spreadsheet()
        print("✅ Kết nối Google Sheet thành công:", ss.title)
        for name in ALL_SHEETS:
            try:
                ws = ss.worksheet(name)
                print(f"✅ {name}: {ws.row_count} dòng")
            except Exception:
                print(f"❌ Không tìm thấy sheet: {name}")
        return True
    except Exception as e:
        print("❌ Lỗi kết nối Google Sheet:", e)
        return False
