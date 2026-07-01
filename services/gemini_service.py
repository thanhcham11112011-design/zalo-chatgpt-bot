# services/gemini_service.py
# Xử lý AI Gemini

from google import genai

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    DEFAULT_REPLY,
)

# ==========================================
# KHỞI TẠO GEMINI
# ==========================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)

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

3. Nếu không chắc chắn:
- Không suy diễn.
- Không bịa.
- Hướng dẫn người dân liên hệ Công an phường.

4. Không trả lời các nội dung ngoài phạm vi pháp luật, thủ tục hành chính và hỗ trợ người dân.
"""


# ==========================================
# TẠO PROMPT
# ==========================================

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


# ==========================================
# GỌI GEMINI
# ==========================================

def ask_gemini(question, context=""):
    try:

        prompt = build_prompt(
            question,
            context
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        if response and response.text:
            return response.text.strip()

        return DEFAULT_REPLY

    except Exception as e:

        print(f"[GEMINI ERROR] {e}")

        return DEFAULT_REPLY


# ==========================================
# TEST
# ==========================================

if __name__ == "__main__":

    print(
        ask_gemini(
            "Thủ tục cấp lại căn cước?"
        )
    )
