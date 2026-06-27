```python
"""
=========================================================
PROJECT : AI AGENT V1 - CÔNG AN PHƯỜNG PHÙ LIỄN
FILE    : services/config.py
VERSION : 1.0.0 Production
AUTHOR  : OpenAI

Chức năng
---------------------------------------------------------
- Đọc biến môi trường (.env)
- Khai báo hằng số hệ thống
- Cấu hình Gemini
- Cấu hình Apps Script API
- Cấu hình Zalo OA
- Timeout
- Logging
=========================================================
"""

import os
from dotenv import load_dotenv

# =========================================================
# LOAD ENVIRONMENT
# =========================================================

load_dotenv()

# =========================================================
# PROJECT INFORMATION
# =========================================================

PROJECT_NAME = "AI Agent V1"

PROJECT_VERSION = "1.0.0"

PROJECT_AUTHOR = "Công an phường Phù Liễn"

PROJECT_ENV = os.getenv("PROJECT_ENV", "production")

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# =========================================================
# FLASK
# =========================================================

HOST = os.getenv("HOST", "0.0.0.0")

PORT = int(os.getenv("PORT", "10000"))

# =========================================================
# GEMINI
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

GEMINI_MODEL = os.getenv(

    "GEMINI_MODEL",

    "gemini-2.5-flash"

)

GEMINI_TEMPERATURE = float(

    os.getenv(

        "GEMINI_TEMPERATURE",

        "0.3"

    )

)

GEMINI_MAX_OUTPUT_TOKENS = int(

    os.getenv(

        "GEMINI_MAX_OUTPUT_TOKENS",

        "2048"

    )

)

# =========================================================
# GOOGLE APPS SCRIPT
# =========================================================

APPS_SCRIPT_URL = os.getenv(

    "APPS_SCRIPT_URL",

    ""

).strip()

APPS_SCRIPT_TIMEOUT = int(

    os.getenv(

        "APPS_SCRIPT_TIMEOUT",

        "30"

    )

)

# =========================================================
# ZALO OA
# =========================================================

ZALO_ACCESS_TOKEN = os.getenv(

    "ZALO_ACCESS_TOKEN",

    ""

).strip()

ZALO_OA_ID = os.getenv(

    "ZALO_OA_ID",

    ""

).strip()

VERIFY_TOKEN = os.getenv(

    "VERIFY_TOKEN",

    ""

).strip()
```

