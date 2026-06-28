import os
from dotenv import load_dotenv

load_dotenv()

ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "credentials.json"
)

OA_NAME = os.getenv(
    "OA_NAME",
    "Công an phường Phù Liễn"
)

PORT = int(os.getenv("PORT", 5000))


def check_config():
    missing = []

    if not ZALO_ACCESS_TOKEN:
        missing.append("ZALO_ACCESS_TOKEN")

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")

    if missing:
        raise RuntimeError(
            "Thiếu biến môi trường: " + ", ".join(missing)
        )
