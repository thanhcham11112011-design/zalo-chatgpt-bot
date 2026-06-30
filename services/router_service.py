# router.py
# Điều hướng câu hỏi người dân sang đúng nguồn dữ liệu

from config import DEFAULT_REPLY
from search_engine import (
    normalize_text,
    search_menu,
    search_lien_he,
    search_faq,
    search_thu_tuc,
    format_lien_he,
    format_faq,
    format_thu_tuc,
    format_multiple_results,
)


def is_greeting(user_text):
    text = normalize_text(user_text)

    greetings = [
        "xin chao",
        "chao",
        "hello",
        "hi",
        "alo",
        "menu",
        "bat dau",
    ]

    return text in greetings


def get_welcome_message():
    return (
        "Xin chào! Đây là Trợ lý ảo Công an phường Phù Liễn.\n\n"
        "Vui lòng nhập nội dung cần hỏi hoặc chọn nhanh:\n"
        "1. Làm căn cước\n"
        "2. Đăng ký cư trú\n"
        "3. VNeID / định danh điện tử\n"
        "4. Phản ánh ANTT\n"
        "5. Số điện thoại trực ban\n"
        "6. Gặp cán bộ trực"
    )


def answer_from_menu(menu_row):
    ten = menu_row.get("TEN_CHUC_NANG", "")
    mo_ta = menu_row.get("MO_TA", "")
    sheet = menu_row.get("SHEET_DU_LIEU", "")

    parts = []

    if ten:
        parts.append(f"📌 {ten}")
    if mo_ta:
        parts.append(mo_ta)
    if sheet:
        parts.append(f"Bạn có thể nhập câu hỏi cụ thể hơn để tôi tra cứu trong nhóm: {sheet}")

    return "\n".join(parts)


def route_message(user_text):
    if not user_text or not str(user_text).strip():
        return DEFAULT_REPLY, "EMPTY"

    text = str(user_text).strip()

    if is_greeting(text):
        return get_welcome_message(), "WELCOME"

    menu_result = search_menu(text)
    if menu_result:
        return answer_from_menu(menu_result), "MENU"

    lien_he_results = search_lien_he(text, limit=3)
    if lien_he_results:
        reply = format_multiple_results(
            lien_he_results,
            format_lien_he,
            limit=3
        )
        return reply, "TRA_CUU_LIEN_HE"

    faq_results = search_faq(text, limit=3)
    if faq_results:
        reply = format_multiple_results(
            faq_results,
            format_faq,
            limit=3
        )
        return reply, "FAQ"

    thu_tuc_results = search_thu_tuc(text, limit=3)
    if thu_tuc_results:
        reply = format_multiple_results(
            thu_tuc_results,
            format_thu_tuc,
            limit=3
        )
        return reply, "THU_TUC"

    return DEFAULT_REPLY, "DEFAULT"


def route_message_for_ai(user_text):
    """
    Hàm này dùng cho app.py:
    - Nếu tìm thấy dữ liệu trong sheet thì trả lời ngay.
    - Nếu không tìm thấy thì trả DEFAULT để app.py gọi Gemini.
    """
    reply, source = route_message(user_text)

    use_ai = source in ["DEFAULT", "EMPTY"]

    return {
        "reply": reply,
        "source": source,
        "use_ai": use_ai,
    }
