"""
=============================================
FILE: config.py
PROJECT: AI AGENT ZALO OA
VERSION: 1.0
=============================================
"""

import os

# ==========================
# GOOGLE SHEETS
# ==========================

GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    ""
)

GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "credentials.json"
)

# ==========================
# GEMINI AI
# ==========================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    ""
)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.0-flash"
)

# ==========================
# ZALO OA
# ==========================

ZALO_ACCESS_TOKEN = os.getenv(
    "ZALO_ACCESS_TOKEN",
    ""
)

ZALO_API_URL = (
    "ZALO_API_URL = (
    "https://openapi.zalo.me/v2.0/oa/message"
)"
)

# ==========================
# FLASK
# ==========================

HOST = "0.0.0.0"

PORT = int(
    os.getenv(
        "PORT",
        10000
    )
)

DEBUG = False

# ==========================
# BOT
# ==========================

BOT_NAME = "Trợ lý AI Công an phường Phù Liễn"

BOT_VERSION = "1.0"

MAX_HISTORY = 10

MAX_REPLY_LENGTH = 1900

# ==========================
# CACHE
# ==========================

CACHE_TIMEOUT = 300

# ==========================
# GOOGLE SHEETS
# ==========================

MENU_SHEET = "MENU"

FAQ_SHEET = "FAQ"

CONTACT_SHEET = "TRA_CUU_LIEN_HE"

INFO_SHEET = "THONGTIN"

PROMPT_SHEET = "PROMPT"

CHAT_LOG_SHEET = "LICH_SU_CHAT"

PROCEDURE_SHEETS = [
    "THU_TUC_ANTT",
    "THU_TUC_CCCD",
    "THU_TUC_CUTRU",
    "THU_TUC_VNEID",
    "THU_TUC_LLTP",
    "THU_TUC_PTGT",
    "THU_TUC_PCCC",
    "THU_TUC_VKVLN"
]

# ==========================
# LOGGING
# ==========================

LOG_LEVEL = "INFO"

LOG_FILE = "bot.log"
