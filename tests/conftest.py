from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Chức năng: Cung cấp bộ cấu hình AI giả lập dùng chung cho các bài test.
# Vai trò: Ngăn test đọc SETTING_AI thật từ Google Sheets.
@pytest.fixture
def ai_settings():
    return {
        "MODEL": "gemini-test",
        "AI_ENABLED": "TRUE",
        "AI_MODE": "OPTIONAL",
        "AI_IS_CORE": "FALSE",
        "AI_STATUS": "ONLINE",
        "STRICT_SHEET_ONLY": "TRUE",
        "ALLOW_AI_WITHOUT_SHEET_CONTEXT": "FALSE",
        "TEMPERATURE": "0.2",
        "TOP_P": "0.9",
        "TOP_K": "40",
        "MAX_OUTPUT_TOKEN": "2048",
        "AI_MAX_OUTPUT_CHARS": "1500",
        "AI_TIMEOUT_SECONDS": "15",
        "AI_MAX_RETRIES": "1",
        "AI_RETRY_DELAY_SECONDS": "1",
        "AI_RETRY_ENABLED": "TRUE",
    }


# Chức năng: Xóa trạng thái Gemini client trước và sau mỗi bài test AI.
# Vai trò: Bảo đảm các bài test không dùng lại client từ bài test trước.
@pytest.fixture
def reset_gemini_state():
    from services import gemini_service

    gemini_service._client = None
    gemini_service._client_signature = ()

    yield

    gemini_service._client = None
    gemini_service._client_signature = ()


# Chức năng: Xóa bộ nhớ chống webhook trùng trước và sau bài test.
# Vai trò: Bảo đảm mỗi bài test message_id chạy độc lập.
@pytest.fixture
def reset_message_dedup():
    import app

    app.processed_messages.clear()

    yield

    app.processed_messages.clear()


# Chức năng: Xóa bộ nhớ session trước và sau mỗi bài test context.
# Vai trò: Ngăn context của bài test trước ảnh hưởng bài test sau.
@pytest.fixture
def reset_session_memory():
    from services import session_manager

    session_manager._memory.clear()

    yield

    session_manager._memory.clear()
