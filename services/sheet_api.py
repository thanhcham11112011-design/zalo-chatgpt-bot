# services/sheet_api.py
# Đọc và ghi dữ liệu Google Sheets cho BOT Công an phường Phù Liễn

import json
import gspread
from google.oauth2.service_account import Credentials

from config import (
    SPREADSHEET_ID,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    ALL_SHEETS,
    THU_TUC_SHEETS,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_client():
    service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
    )

    return gspread.authorize(credentials)


def get_spreadsheet():
    client = get_client()
    return client.open_by_key(SPREADSHEET_ID)


def get_worksheet(sheet_name):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)


def read_sheet(sheet_name):
    try:
        worksheet = get_worksheet(sheet_name)
        return worksheet.get_all_records()
    except Exception as e:
        print(f"[SHEET ERROR] Không đọc được sheet {sheet_name}: {e}")
        return []


def is_on(row):
    status = str(row.get("TRANG_THAI", "ON")).strip().upper()
    return status == "ON"


def read_active_rows(sheet_name):
    rows = read_sheet(sheet_name)
    return [row for row in rows if is_on(row)]


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


def read_lien_he():
    return read_active_rows("TRA_CUU_LIEN_HE")


def read_faq():
    return read_active_rows("FAQ")


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


def append_row(sheet_name, values):
    try:
        worksheet = get_worksheet(sheet_name)
        worksheet.append_row(values)
        return True
    except Exception as e:
        print(f"[SHEET ERROR] Không ghi được sheet {sheet_name}: {e}")
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
