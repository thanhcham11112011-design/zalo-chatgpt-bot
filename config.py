import os
from dotenv import load_dotenv

load_dotenv()

# Chức năng: Đọc biến môi trường kỹ thuật khi BOT khởi động.
# Vai trò: Giữ config.py chỉ làm lớp cấu hình hạ tầng, không chứa nghiệp vụ.
PORT = int(os.getenv("PORT", "5000"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "FALSE").strip().upper() == "TRUE"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "").strip()

# Chức năng: Cấu hình kết nối Google Sheets.
# Vai trò: Google Sheets là nguồn dữ liệu nghiệp vụ duy nhất của BOT CAP 3.1.
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json").strip()
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()

# Chức năng: Cấu hình kỹ thuật cho AI.
# Vai trò: API/model được cấu hình bằng biến môi trường, prompt và nghiệp vụ đọc từ sheet PROMPT/SETTING_AI.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip()

# Chức năng: Cấu hình kết nối Zalo OA.
# Vai trò: Cung cấp tham số kỹ thuật để gửi/nhận tin nhắn Zalo.
ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN", "").strip()
ZALO_APP_ID = os.getenv("ZALO_APP_ID", "").strip()
ZALO_APP_SECRET = os.getenv("ZALO_APP_SECRET", "").strip()
ZALO_REFRESH_TOKEN = os.getenv("ZALO_REFRESH_TOKEN", "").strip()
ZALO_OA_SECRET_KEY = (
    os.getenv("ZALO_OA_SECRET_KEY", "").strip()
    or ZALO_APP_SECRET
)
ZALO_WEBHOOK_VERIFY_SIGNATURE = (
    os.getenv(
        "ZALO_WEBHOOK_VERIFY_SIGNATURE",
        "TRUE",
    ).strip().upper()
    in {"1", "TRUE", "YES", "ON"}
)

# Chức năng: Khai báo tên các sheet lõi của hệ thống.
# Vai trò: Đây là hằng số kỹ thuật để sheet_api.py truy cập dữ liệu, không phải dữ liệu nghiệp vụ.
SHEET_MENU = "MENU"
SHEET_FILTER_BAD_WORD = "FILTER_BAD_WORD"
SHEET_SETTING_SYSTEM = "SETTING_SYSTEM"
SHEET_SETTING_AI = "SETTING_AI"
SHEET_SETTING_CHAT = "SETTING_CHAT"
SHEET_PROMPT = "PROMPT"
SHEET_THONGTIN = "THONGTIN"
SHEET_TRA_CUU_LIEN_HE = "TRA_CUU_LIEN_HE"
SHEET_FAQ = "FAQ"
SHEET_LICH_SU_CHAT = "LICH_SU_CHAT"
SHEET_SESSION = "BOT_SESSION"
SHEET_SURVEY = "KHAO_SAT"
SHEET_SURVEY_QUESTIONS = "CAU_HOI_KHAO_SAT"
SHEET_SURVEY_RESULTS = "KET_QUA_KHAO_SAT"
SHEET_WEBHOOK_EVENT = os.getenv(
    "SHEET_WEBHOOK_EVENT",
    "BOT_WEBHOOK_EVENT",
).strip()
SHEET_DATA_DICTIONARY = "DATA_DICTIONARY"
SHEET_BOT_31_SCHEMA = "BOT_31_SCHEMA"

# Chức năng: Danh sách sheet lõi cần kiểm tra khi health-check.
# Vai trò: Không chứa danh sách THU_TUC_* hardcode; sheet thủ tục lấy động từ MENU.SHEET_DU_LIEU.
CORE_SHEETS = [
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
]

# Chức năng: Cấu hình kỹ thuật cho phiên chat và giới hạn tin nhắn.
# Vai trò: Điều khiển vận hành hệ thống, không chứa nội dung trả lời nghiệp vụ.
SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "60"))
MAX_ZALO_TEXT_LENGTH = int(os.getenv("MAX_ZALO_TEXT_LENGTH", "1900"))
SHEET_CACHE_TTL_SECONDS = int(os.getenv("SHEET_CACHE_TTL_SECONDS", "30"))
WEBHOOK_EVENT_MAX_ROWS = max(
    1000,
    int(os.getenv("WEBHOOK_EVENT_MAX_ROWS", "10000")),
)
WEBHOOK_DEDUP_FAIL_CLOSED = (
    os.getenv(
        "WEBHOOK_DEDUP_FAIL_CLOSED",
        "TRUE",
    ).strip().upper()
    in {"1", "TRUE", "YES", "ON"}
)

# Chức năng: Thông báo kỹ thuật tối thiểu khi hệ thống lỗi nặng.
# Vai trò: Fallback an toàn cấp hệ thống; nội dung hội thoại chính đọc từ SETTING_CHAT.
TECHNICAL_FALLBACK_REPLY = os.getenv(
    "TECHNICAL_FALLBACK_REPLY",
    "Hệ thống đang tạm thời bận. Quý công dân vui lòng thử lại sau."
).strip()


def check_config():
    # Chức năng: Kiểm tra các biến môi trường bắt buộc và nguồn credentials thực tế.
    # Vai trò: Phát hiện cấu hình deploy thiếu trước khi BOT kết nối Google Sheets và Zalo.
    missing = []

    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")

    credentials_file_exists = bool(
        GOOGLE_CREDENTIALS_FILE
        and os.path.isfile(GOOGLE_CREDENTIALS_FILE)
    )
    if not GOOGLE_CREDENTIALS_JSON and not credentials_file_exists:
        missing.append("GOOGLE_CREDENTIALS_JSON hoặc GOOGLE_CREDENTIALS_FILE hợp lệ")

    if not ZALO_ACCESS_TOKEN:
        missing.append("ZALO_ACCESS_TOKEN")

    if ZALO_WEBHOOK_VERIFY_SIGNATURE:
        if not ZALO_APP_ID:
            missing.append("ZALO_APP_ID")
        if not ZALO_OA_SECRET_KEY:
            missing.append("ZALO_OA_SECRET_KEY hoặc ZALO_APP_SECRET")

    if not INTERNAL_API_KEY:
        missing.append("INTERNAL_API_KEY")

    return len(missing) == 0, missing


def is_debug_mode():
    # Chức năng: Trả về trạng thái debug.
    # Vai trò: Giúp các module khác kiểm tra chế độ vận hành kỹ thuật.
    return DEBUG_MODE
