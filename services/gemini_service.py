import os
from google import genai


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


class GeminiService:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("Thiếu biến môi trường GEMINI_API_KEY")

        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def build_prompt(self, question, context_items=None, history_text=""):
        context_items = context_items or []

        context_text = ""

        for i, item in enumerate(context_items, start=1):
            context_text += f"\n--- Dữ liệu {i} ---\n"
            for key, value in item.items():
                if value:
                    context_text += f"{key}: {value}\n"

        return f"""
Bạn là trợ lý ảo của Công an phường Phù Liễn.

Nhiệm vụ:
- Trả lời ngắn gọn, rõ ràng, lịch sự.
- Ưu tiên trả lời dựa trên dữ liệu được cung cấp.
- Nếu chưa đủ thông tin, hướng dẫn người dân liên hệ Công an phường.
- Không bịa thông tin ngoài dữ liệu.

Dữ liệu tham khảo:
{context_text}

Lịch sử hội thoại:
{history_text}

Câu hỏi của người dân:
{question}

Hãy trả lời bằng tiếng Việt:
"""

    def ask(self, question, context_items=None, history_text=""):
        try:
            prompt = self.build_prompt(
                question=question,
                context_items=context_items,
                history_text=history_text
            )

            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )

            if hasattr(response, "text") and response.text:
                return response.text.strip()

            return (
                "Xin lỗi, hiện hệ thống chưa tạo được câu trả lời. "
                "Quý công dân vui lòng thử lại sau."
            )

        except Exception as e:
            print("GEMINI ERROR:", e)

            return (
                "Xin lỗi, hiện hệ thống AI đang bận. "
                "Quý công dân vui lòng thử lại sau hoặc liên hệ Công an phường để được hỗ trợ."
            )


gemini_service = GeminiService()
