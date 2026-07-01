# services/gemini_service.py
# Xử lý AI Gemini

from google import genai

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    DEFAULT_REPLY,
)

from services.sheet_api import read_setting_system

_client = None


SYSTEM_PROMPT = """
Bạn là Trợ lý AI của Công an phường Phù Liễn, thành phố Hải Phòng.

Nhiệm vụ:
- Hỗ trợ người dân tra cứu thủ tục hành chính.
- Hướng dẫn hồ sơ, điều kiện, trình tự, nơi nộp.
- Trả lời ngắn gọn, rõ ràng, dễ hiểu.
- Không tự bịa thông tin.

Nguyên tắc:
1. Nếu dữ liệu Google Sheet đã có câu trả lời thì ưu tiên dữ liệu đó.
2. Chỉ sử dụng AI khi Router không tìm thấy dữ liệu.
3. Nếu không chắc chắn: không suy diễn, không bịa; hướng dẫn người dân liên hệ Công an phường.
4. Không trả lời các nội dung ngoài phạm vi pháp luật, thủ tục hành chính và hỗ trợ người dân.
"""


def _get_ai_config():
    settings = read_setting_system()
    api_key = str(settings.get("GEMINI_API_KEY") or GEMINI_API_KEY or "").strip()
    model = str(settings.get("GEMINI_MODEL") or GEMINI_MODEL or "gemini-2.0-flash").strip()
    return api_key, model


def _get_client():
    global _client

    if _client:
        return _client

    api_key, _ = _get_ai_config()

    if not api_key:
        return None

    _client = genai.Client(api_key=api_key)
    return _client


def build_prompt(question, context=""):
    if context:
        return f"""
{SYSTEM_PROMPT}

====================
DỮ LIỆU THAM KHẢO
====================

{context}

====================
CÂU HỎI
====================

{question}

====================
YÊU CẦU
====================

- Trả lời ngắn gọn.
- Dễ hiểu.
- Không quá 1500 ký tự.
"""

    return f"""
{SYSTEM_PROMPT}

====================
CÂU HỎI
====================

{question}

====================
YÊU CẦU
====================

Nếu không có đủ thông tin thì trả lời theo hướng dẫn chung.
Không được tự bịa thông tin.
Không quá 1500 ký tự.
"""


def ask_gemini(question, context=""):
    try:
        client = _get_client()
        _, model = _get_ai_config()

        if not client:
            print("[GEMINI ERROR] Thiếu GEMINI_API_KEY")
            return DEFAULT_REPLY

        prompt = build_prompt(question, context)

        response = client.models.generate_content(
            model=model,
            contents=prompt
        )

        if response and response.text:
            return response.text.strip()

        return DEFAULT_REPLY

    except Exception as e:
        print(f"[GEMINI ERROR] {e}")
        return DEFAULT_REPLY


if __name__ == "__main__":
    print(ask_gemini("Thủ tục cấp lại căn cước?"))
