# services/gemini_service.py
# Xử lý trả lời AI bằng Gemini

from google import genai

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    DEFAULT_REPLY,
)


client = genai.Client(api_key=GEMINI_API_KEY)


SYSTEM_INSTRUCTION = """
Bạn là Trợ lý AI của Công an phường Phù Liễn, thành phố Hải Phòng.

Nhiệm vụ:
- Hỗ trợ người dân tra cứu thủ tục hành chính.
- Hướng dẫn hồ sơ, nơi nộp, thời hạn, lệ phí, kết quả thực hiện.
- Hỗ trợ tra cứu thông tin liên hệ khi có dữ liệu.
- Trả lời ngắn gọn, rõ ràng, dễ hiểu trên Zalo.

Nguyên tắc:
- Ưu tiên dữ liệu từ Google Sheets.
- Không tự bịa số điện thoại, địa chỉ, lệ phí, thời hạn hoặc căn cứ pháp lý.
- Nếu không chắc chắn, hướng dẫn người dân liên hệ trực ban Công an phường để được hỗ trợ.
"""


def build_prompt(user_message, context=""):
    if context:
        return f"""
{SYSTEM_INSTRUCTION}

Dữ liệu tham khảo:
{context}

Câu hỏi của người dân:
{user_message}

Yêu cầu:
Trả lời ngắn gọn, dễ hiểu, không vượt quá 1.500 ký tự.
"""
    return f"""
{SYSTEM_INSTRUCTION}

Câu hỏi của người dân:
{user_message}

Yêu cầu:
Nếu không có đủ dữ liệu chắc chắn, hãy trả lời theo hướng dẫn chung.
Không tự bịa thông tin.
Trả lời không vượt quá 1.500 ký tự.
"""


def ask_gemini(user_message, context=""):
    try:
        prompt = build_prompt(user_message, context)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        if response and response.text:
            return response.text.strip()

        return DEFAULT_REPLY

    except Exception as e:
        print(f"[GEMINI ERROR] {e}")
        return DEFAULT_REPLY
