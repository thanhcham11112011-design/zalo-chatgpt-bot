import os
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PORT", 5000))
BOT_NAME = os.getenv("BOT_NAME", "Trợ lý AI Công an phường Phù Liễn").strip()
DEFAULT_REPLY = os.getenv(
    "DEFAULT_REPLY",
    "Xin lỗi, hiện tôi chưa hiểu rõ ý định câu hỏi hoặc hệ thống AI đang tạm thời không khả dụng.\n\n"
                "Quý công dân vui lòng nhập rõ nội dung cần hỗ trợ, ví dụ:\n"
                "• Làm căn cước ở đâu\n"
                "• Đăng ký tạm trú cần giấy tờ gì\n"
                "• Số điện thoại Công an phường\n"
                "• menu"
).strip()

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json").strip()
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN", "").strip()
ZALO_APP_ID = os.getenv("ZALO_APP_ID", "").strip()
ZALO_APP_SECRET = os.getenv("ZALO_APP_SECRET", "").strip()
ZALO_REFRESH_TOKEN = os.getenv("ZALO_REFRESH_TOKEN", "").strip()

SHEET_MENU = "MENU"
SHEET_SETTING_SYSTEM = "SETTING_SYSTEM"
SHEET_SETTING_AI = "SETTING_AI"
SHEET_SETTING_CHAT = "SETTING_CHAT"
SHEET_PROMPT = "PROMPT"
SHEET_THONGTIN = "THONGTIN"
SHEET_TRA_CUU_LIEN_HE = "TRA_CUU_LIEN_HE"
SHEET_FAQ = "FAQ"
SHEET_LICH_SU_CHAT = "LICH_SU_CHAT"
SHEET_SESSION = "BOT_SESSION"

THU_TUC_SHEETS = [
    "THU_TUC_CCCD",
    "THU_TUC_CUTRU",
    "THU_TUC_VNEID",
    "THU_TUC_LLTP",
    "THU_TUC_PTGT",
    "THU_TUC_PCCC",
    "THU_TUC_VKVLN",
    "THU_TUC_ANTT",
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
    SHEET_SESSION,
    *THU_TUC_SHEETS,
]

SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", 60))
MAX_ZALO_TEXT_LENGTH = int(os.getenv("MAX_ZALO_TEXT_LENGTH", 1900))


def check_config():
    missing = []
    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")
    if not GOOGLE_CREDENTIALS_JSON and not GOOGLE_CREDENTIALS_FILE:
        missing.append("GOOGLE_CREDENTIALS_JSON hoặc GOOGLE_CREDENTIALS_FILE")
    return len(missing) == 0, missing
