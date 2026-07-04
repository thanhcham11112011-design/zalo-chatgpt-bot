from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, DEFAULT_REPLY
from services.sheet_api import read_setting_system, read_setting_ai, read_prompt

_client = None
_client_api_key = ""


DEFAULT_SYSTEM_PROMPT = """
Bạn là Trợ lý AI của Công an phường Phù Liễn, thành phố Hải Phòng.
Nhiệm vụ: hỗ trợ người dân tra cứu thủ tục hành chính, hồ sơ, trình tự, nơi nộp, thời hạn, lệ phí.
Nguyên tắc:
- Ưu tiên dữ liệu Google Sheets nếu có.
- Không bịa thông tin.
- Không tự tạo số điện thoại, địa chỉ, tên cán bộ, thủ tục hoặc căn cứ pháp lý.
- Nếu không chắc chắn, hướng dẫn người dân liên hệ Công an phường để được hỗ trợ.
- Trả lời ngắn gọn, dễ hiểu, lịch sự.
"""


def _get_ai_config():
    # Chức năng: Đọc cấu hình AI từ Google Sheets và biến môi trường.
    # Vai trò: Giúp BOT ưu tiên cấu hình động trong SETTING_AI/SETTING_SYSTEM, hạn chế hardcode.
    try:
        system_settings = read_setting_system()
    except Exception:
        system_settings = {}

    try:
        ai_settings = read_setting_ai()
    except Exception:
        ai_settings = {}

    api_key = str(
        ai_settings.get("GEMINI_API_KEY")
        or system_settings.get("GEMINI_API_KEY")
        or GEMINI_API_KEY
        or ""
    ).strip()

    model = str(
        ai_settings.get("MODEL")
        or ai_settings.get("GEMINI_MODEL")
        or system_settings.get("GEMINI_MODEL")
        or GEMINI_MODEL
        or "gemini-2.0-flash"
    ).strip()

    return api_key, model


def _get_system_prompt():
    # Chức năng: Đọc SYSTEM prompt từ sheet PROMPT.
    # Vai trò: Cho phép điều chỉnh vai trò AI bằng Google Sheets mà không sửa code.
    try:
        prompts = read_prompt()
    except Exception:
        prompts = {}

    prompt = (
        prompts.get("SYSTEM")
        or prompts.get("DEFAULT")
        or prompts.get("AI_SYSTEM")
        or DEFAULT_SYSTEM_PROMPT
    )

    return str(prompt or DEFAULT_SYSTEM_PROMPT).strip()


def _get_client():
    # Chức năng: Khởi tạo Gemini client theo API key hiện hành.
    # Vai trò: Tái sử dụng client và tự làm mới khi API key thay đổi trong cấu hình.
    global _client, _client_api_key

    api_key, _ = _get_ai_config()
    if not api_key:
        return None

    if _client and _client_api_key == api_key:
        return _client

    _client = genai.Client(api_key=api_key)
    _client_api_key = api_key
    return _client


# Chức năng: Xây dựng Prompt gửi tới Gemini.
# Vai trò: Kết hợp SYSTEM Prompt, dữ liệu Google Sheets và câu hỏi người dân để AI chỉ trả lời trong phạm vi được phép.
def build_prompt(question, context=""):
    system_prompt = _get_system_prompt()

    question = str(question or "").strip()
    context = str(context or "").strip()

    if context:
        return f"""
{system_prompt}

========================
DỮ LIỆU GOOGLE SHEETS
========================

{context}

========================
CÂU HỎI CỦA NGƯỜI DÂN
========================

{question}

========================
YÊU CẦU
========================

1. Ưu tiên tuyệt đối dữ liệu Google Sheets ở trên.
2. Không được tự tạo thêm thông tin ngoài dữ liệu nếu dữ liệu đã đầy đủ.
3. Nếu dữ liệu còn thiếu thì chỉ bổ sung kiến thức pháp luật phổ thông, không suy diễn.
4. Không được tự tạo:
- tên cán bộ;
- số điện thoại;
- địa chỉ;
- thời hạn;
- lệ phí;
- căn cứ pháp lý;
- biểu mẫu.
5. Nếu không đủ căn cứ thì hướng dẫn người dân liên hệ Công an phường để được hỗ trợ.
6. Trả lời bằng tiếng Việt.
7. Văn phong ngắn gọn, lịch sự, dễ hiểu.
8. Độ dài tối đa khoảng 1.500 ký tự.
"""

    return f"""
{system_prompt}

========================
CÂU HỎI CỦA NGƯỜI DÂN
========================

{question}

========================
YÊU CẦU
========================

1. Nếu không có dữ liệu Google Sheets thì chỉ trả lời theo kiến thức pháp luật phổ thông.
2. Không được bịa thông tin.
3. Không được tự tạo tên cán bộ, số điện thoại, địa chỉ hoặc thủ tục hành chính.
4. Nếu không chắc chắn thì trả lời rằng chưa có đủ thông tin và hướng dẫn người dân liên hệ Công an phường.
5. Trả lời bằng tiếng Việt.
6. Văn phong ngắn gọn, lịch sự, dễ hiểu.
7. Độ dài tối đa khoảng 1.500 ký tự.
"""


# Chức năng: Gửi câu hỏi tới Gemini và nhận kết quả trả lời.
# Vai trò: Chỉ gọi AI khi Router xác định cần AI fallback; ưu tiên dữ liệu Google Sheets và xử lý lỗi an toàn.
def ask_gemini(question, context=""):
    try:
        client = _get_client()
        api_key, model = _get_ai_config()

        if not client:
            print("[GEMINI ERROR] Thiếu GEMINI_API_KEY")
            return DEFAULT_REPLY

        prompt = build_prompt(question, context)

        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )

        if not response:
            print("[GEMINI ERROR] Empty response")
            return DEFAULT_REPLY

        text = getattr(response, "text", None)

        if text:
            text = str(text).strip()

            if text:
                return text

        candidates = getattr(response, "candidates", None)
        if candidates:
            try:
                parts = candidates[0].content.parts
                answer = "".join(
                    getattr(part, "text", "")
                    for part in parts
                    if getattr(part, "text", "")
                ).strip()

                if answer:
                    return answer
            except Exception:
                pass

        return DEFAULT_REPLY

    except Exception as e:
        print(f"[GEMINI ERROR] {type(e).__name__}: {e}")
        return DEFAULT_REPLY
