# config.py
# Cấu hình hệ thống BOT Công an phường Phù Liễn

import os
from dotenv import load_dotenv

load_dotenv()


# =========================
# FLASK
# =========================

PORT = int(os.getenv("PORT", 5000))


# =========================
# ZALO OA
# =========================

ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN", "").strip()


# =========================
# GOOGLE SHEETS
# =========================

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    ""
).strip()


# =========================
# GEMINI AI
# =========================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.0-flash"
).strip()


# =========================
# BOT SETTINGS
# =========================

BOT_NAME = os.getenv(
    "BOT_NAME",
    "Trợ lý ảo Công an phường Phù Liễn"
).strip()

DEFAULT_REPLY = os.getenv(
    "DEFAULT_REPLY",
    "Xin lỗi, tôi chưa tìm thấy thông tin phù hợp. Vui lòng nhập lại nội dung cần hỏi hoặc liên hệ trực ban Công an phường để được hỗ trợ."
).strip()


# =========================
# GOOGLE SHEET NAMES
# =========================

SHEET_MENU = "MENU"
SHEET_SETTING_SYSTEM = "SETTING_SYSTEM"
SHEET_SETTING_AI = "SETTING_AI"
SHEET_SETTING_CHAT = "SETTING_CHAT"
SHEET_PROMPT = "PROMPT"
SHEET_THONGTIN = "THONGTIN"
SHEET_TRA_CUU_LIEN_HE = "TRA_CUU_LIEN_HE"
SHEET_FAQ = "FAQ"
SHEET_LICH_SU_CHAT = "LICH_SU_CHAT"

SHEET_THU_TUC_CCCD = "THU_TUC_CCCD"
SHEET_THU_TUC_CUTRU = "THU_TUC_CUTRU"
SHEET_THU_TUC_VNEID = "THU_TUC_VNEID"
SHEET_THU_TUC_LLTP = "THU_TUC_LLTP"
SHEET_THU_TUC_PTGT = "THU_TUC_PTGT"
SHEET_THU_TUC_PCCC = "THU_TUC_PCCC"
SHEET_THU_TUC_VKVLN = "THU_TUC_VKVLN"
SHEET_THU_TUC_ANTT = "THU_TUC_ANTT"


THU_TUC_SHEETS = [
    SHEET_THU_TUC_CCCD,
    SHEET_THU_TUC_CUTRU,
    SHEET_THU_TUC_VNEID,
    SHEET_THU_TUC_LLTP,
    SHEET_THU_TUC_PTGT,
    SHEET_THU_TUC_PCCC,
    SHEET_THU_TUC_VKVLN,
    SHEET_THU_TUC_ANTT,
]


ALL_SHEETS = [
    SHEET_MENU,
    SHEET_SETTING_SYSTEM,
    SHEET_SETTING_AI,
    SHEET_SETTING_CHAT,
    SHEET_PROMPT,
    SHEET_THONGTIN,
    SHEET_TRA_CUU_LIEN_HE,
    SHEET_FAQ,
    SHEET_LICH_SU_CHAT,
    *THU_TUC_SHEETS,
]


# =========================
# VALIDATION
# =========================

def check_config():
    missing = []

    if not ZALO_ACCESS_TOKEN:
        missing.append("ZALO_ACCESS_TOKEN")

    if not SPREADSHEET_ID:
        missing.append("SPREADSHEET_ID")

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        return False, missing

    return True, []


if __name__ == "__main__":
    ok, missing_keys = check_config()

    if ok:
        print("✅ Cấu hình đầy đủ.")
    else:
        print("❌ Thiếu cấu hình:")
        for key in missing_keys:
            print("-", key)
