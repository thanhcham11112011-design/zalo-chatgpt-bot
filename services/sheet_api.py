# services/sheet_api.py
# Đọc và ghi dữ liệu Google Sheets cho BOT Công an phường Phù Liễn

import os
import json
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    ALL_SHEETS,
    THU_TUC_SHEETS,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client_cache = None
_spreadsheet_cache = None


# =========================
# KẾT NỐI GOOGLE SHEETS
# =========================

def _build_credentials():
    """
    Ưu tiên 1: GOOGLE_CREDENTIALS_JSON nếu có JSON service account.
    Ưu tiên 2: GOOGLE_CREDENTIALS_FILE nếu là đường dẫn file credentials.json / Render Secret File.
    """
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()

    if credentials_json:
        creds_dict = json.loads(credentials_json)
        return Credentials.from_service_account_info(
            creds_dict,
            scopes=SCOPES
        )

    return Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES
    )


def get_client():
    global _client_cache

    if _client_cache:
        return _client_cache

    credentials = _build_credentials()
    _client_cache = gspread.authorize(credentials)
    return _client_cache


def get_spreadsheet():
    global _spreadsheet_cache

    if _spreadsheet_cache:
        return _spreadsheet_cache

    client = get_client()
    _spreadsheet_cache = client.open_by_key(GOOGLE_SHEET_ID)
    return _spreadsheet_cache


def get_worksheet(sheet_name):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)


# =========================
# ĐỌC DỮ LIỆU
# =========================

def read_sheet(sheet_name):
    try:
        worksheet = get_worksheet(sheet_name)
        return worksheet.get_all_records()
    except Exception as e:
        print(f"[SHEET ERROR] Không đọc được sheet {sheet_name}: {e}")
        return []


def is_on(row):
    status = (
        row.get("TRANG_THAI")
        or row.get("STATUS")
        or row.get("TRẠNG_THÁI")
        or "ON"
    )
    return str(status).strip().upper() in ("ON", "ACTIVE", "HOẠT ĐỘNG", "HOAT DONG", "1", "TRUE")


def read_active_rows(sheet_name):
    rows = read_sheet(sheet_name)
    return [row for row in rows if is_on(row)]


# =========================
# CÁC SHEET CẤU HÌNH
# =========================

def read_menu():
    return read_active_rows("MENU")


def read_settings(sheet_name):
    rows = read_active_rows(sheet_name)
    data = {}

    for row in rows:
        key = str(row.get("KEY", "")).strip()
        value = row.get("VALUE", "")

        if key:
            data[key] = value

    return data


def read_setting_system():
    return read_settings("SETTING_SYSTEM")


def read_setting_ai():
    return read_settings("SETTING_AI")


def read_setting_chat():
    return read_settings("SETTING_CHAT")


def read_prompts():
    rows = read_active_rows("PROMPT")
    data = {}

    for row in rows:
        key = str(row.get("PROMPT_NAME", "")).strip()
        value = str(row.get("NOI_DUNG", "")).strip()

        if key:
            data[key] = value

    return data


def read_thongtin():
    rows = read_active_rows("THONGTIN")
    data = {}

    for row in rows:
        key = str(row.get("KEY", "")).strip()
        value = row.get("VALUE", "")

        if key:
            data[key] = value

    return data


# =========================
# SHEET TRA CỨU
# =========================

def read_lien_he():
    return read_active_rows("TRA_CUU_LIEN_HE")


def read_faq():
    return read_active_rows("FAQ")


# =========================
# SHEET THỦ TỤC
# =========================

def read_thu_tuc_sheet(sheet_name):
    return read_active_rows(sheet_name)


def read_all_thu_tuc():
    data = []

    for sheet_name in THU_TUC_SHEETS:
        rows = read_active_rows(sheet_name)

        for row in rows:
            row["_SHEET"] = sheet_name
            data.append(row)

    return data


# =========================
# GHI DỮ LIỆU
# =========================

def append_row(sheet_name, values):
    try:
        worksheet = get_worksheet(sheet_name)
        worksheet.append_row(values)
        return True
    except Exception as e:
        print(f"[SHEET ERROR] Không ghi được sheet {sheet_name}: {e}")
        return False


def update_setting_system(key, value):
    """
    Cập nhật KEY/VALUE trong SETTING_SYSTEM.
    Nếu KEY chưa có thì append dòng mới: KEY | VALUE | DESCRIPTION | STATUS
    """
    try:
        worksheet = get_worksheet("SETTING_SYSTEM")
        values = worksheet.get_all_values()

        if not values:
            worksheet.append_row(["KEY", "VALUE", "DESCRIPTION", "STATUS"])
            values = worksheet.get_all_values()

        header = [h.strip() for h in values[0]]
        key_col = header.index("KEY") + 1 if "KEY" in header else 1
        value_col = header.index("VALUE") + 1 if "VALUE" in header else 2

        for idx, row in enumerate(values[1:], start=2):
            if len(row) >= key_col and row[key_col - 1].strip() == key:
                worksheet.update_cell(idx, value_col, value)
                return True

        worksheet.append_row([key, value, "", "ON"])
        return True

    except Exception as e:
        print(f"[SHEET ERROR] Không cập nhật SETTING_SYSTEM {key}: {e}")
        return False


def log_chat(thoi_gian, user_id, user_message, bot_reply, source="BOT"):
    values = [
        thoi_gian,
        user_id,
        user_message,
        bot_reply,
        source,
    ]

    return append_row("LICH_SU_CHAT", values)


# =========================
# KIỂM TRA KẾT NỐI
# =========================

def test_connection():
    try:
        spreadsheet = get_spreadsheet()

        print("✅ Kết nối Google Sheet thành công")
        print("Tên file:", spreadsheet.title)

        for sheet_name in ALL_SHEETS:
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                print(f"✅ {sheet_name}: {worksheet.row_count} dòng")
            except Exception:
                print(f"❌ Không tìm thấy sheet: {sheet_name}")

        return True

    except Exception as e:
        print("❌ Lỗi kết nối Google Sheet:", e)
        return False


if __name__ == "__main__":
    test_connection()
