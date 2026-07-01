# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# =========================
# FLASK
# =========================

PORT = int(os.getenv("PORT", 5000))

# =========================
# BOT
# =========================

BOT_NAME = os.getenv(
    "BOT_NAME",
    "Trợ lý AI Công an phường Phù Liễn"
).strip()

DEFAULT_REPLY = os.getenv(
    "DEFAULT_REPLY",
    "Xin lỗi, tôi chưa tìm thấy thông tin phù hợp. Vui lòng liên hệ Công an phường để được hỗ trợ."
).strip()

# =========================
# GOOGLE SHEETS
# =========================

GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    ""
).strip()

GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "credentials.json"
).strip()

# =========================
# GEMINI
# =========================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    ""
).strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.0-flash"
).strip()

# =========================
# ZALO OA
# =========================

ZALO_ACCESS_TOKEN = os.getenv(
    "ZALO_ACCESS_TOKEN",
    ""
).strip()
ZALO_APP_ID = os.getenv(
    "ZALO_APP_ID",
    ""
).strip()

ZALO_APP_SECRET = os.getenv(
    "ZALO_APP_SECRET",
    ""
).strip()

ZALO_REFRESH_TOKEN = os.getenv(
    "ZALO_REFRESH_TOKEN",
    ""
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
# CHECK CONFIG
# =========================

def check_config():
    missing = []

    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")

    if not GOOGLE_CREDENTIALS_FILE:
        missing.append("GOOGLE_CREDENTIALS_FILE")

    # GEMINI_API_KEY, ZALO_ACCESS_TOKEN, ZALO_REFRESH_TOKEN có thể được đọc từ Google Sheet SETTING_SYSTEM.
    # Không bắt buộc khai báo trong Render Environment nữa.

    return len(missing) == 0, missing


if __name__ == "__main__":
    ok, missing = check_config()

    if ok:
        print("✅ CONFIG OK")
    else:
        print("❌ Thiếu cấu hình:")
        for item in missing:
            print("-", item)
