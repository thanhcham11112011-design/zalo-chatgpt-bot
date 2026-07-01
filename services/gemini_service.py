from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, DEFAULT_REPLY
from services.sheet_api import read_setting_system

_client = None

SYSTEM_PROMPT = """
Bạn là Trợ lý AI của Công an phường Phù Liễn, thành phố Hải Phòng.
Nhiệm vụ: hỗ trợ người dân tra cứu thủ tục hành chính, hồ sơ, trình tự, nơi nộp, thời hạn, lệ phí.
Nguyên tắc:
- Ưu tiên dữ liệu Google Sheet nếu có.
- Không bịa thông tin.
- Nếu không chắc chắn, hướng dẫn người dân liên hệ Công an phường để được hỗ trợ.
- Trả lời ngắn gọn, dễ hiểu, lịch sự.
"""


def _get_ai_config():
    try:
        settings = read_setting_system()
    except Exception:
        settings = {}
    api_key = str(settings.get("GEMINI_API_KEY") or GEMINI_API_KEY or "").strip()
    model = str(settings.get("GEMINI_MODEL") or GEMINI_MODEL or "gemini-2.0-flash").strip()
    return api_key, model


def _get_client():
    global _client
    api_key, _ = _get_ai_config()
    if not api_key:
        return None
    if _client:
        return _client
    _client = genai.Client(api_key=api_key)
    return _client


def build_prompt(question, context=""):
    if context:
        return f"""
{SYSTEM_PROMPT}

DỮ LIỆU THAM KHẢO:
{context}

CÂU HỎI CỦA NGƯỜI DÂN:
{question}

YÊU CẦU:
- Chỉ trả lời theo dữ liệu tham khảo nếu dữ liệu đủ.
- Không quá 1500 ký tự.
"""
    return f"""
{SYSTEM_PROMPT}

CÂU HỎI CỦA NGƯỜI DÂN:
{question}

YÊU CẦU:
- Nếu không có đủ thông tin thì không suy diễn.
- Không quá 1500 ký tự.
"""


def ask_gemini(question, context=""):
    try:
        client = _get_client()
        _, model = _get_ai_config()
        if not client:
            print("[GEMINI ERROR] Thiếu GEMINI_API_KEY")
            return DEFAULT_REPLY
        response = client.models.generate_content(model=model, contents=build_prompt(question, context))
        if response and getattr(response, "text", None):
            return response.text.strip()
        return DEFAULT_REPLY
    except Exception as e:
        print(f"[GEMINI ERROR] {e}")
        return DEFAULT_REPLY
