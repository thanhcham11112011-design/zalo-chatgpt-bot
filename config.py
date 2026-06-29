import os

# GEMINI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# GOOGLE SHEETS
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")

# ZALO OA
ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN", "")
ZALO_REFRESH_TOKEN = os.getenv("ZALO_REFRESH_TOKEN", "")
ZALO_APP_ID = os.getenv("ZALO_APP_ID", "")
ZALO_APP_SECRET = os.getenv("ZALO_APP_SECRET", "")

# BOT
BOT_NAME = os.getenv("BOT_NAME", "Trợ lý AI Công an phường Phù Liễn")
BOT_VERSION = os.getenv("BOT_VERSION", "1.0")
UNIT_NAME = os.getenv("UNIT_NAME", "Công an phường Phù Liễn")
CITY = os.getenv("CITY", "Hải Phòng")

# CHAT
MAX_REPLY_LENGTH = int(os.getenv("MAX_REPLY_LENGTH", "1900"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))

# FLASK
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "10000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
