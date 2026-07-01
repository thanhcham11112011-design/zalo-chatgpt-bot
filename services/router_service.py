# services/router_service.py
# Điều hướng câu hỏi người dân sang đúng nguồn dữ liệu

from config import DEFAULT_REPLY
from services.sheet_api import read_menu

from services.search_engine import (
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


# =========================
# NHẬN DIỆN LỜI CHÀO / MENU
# =========================

def is_greeting(user_text):
    text = normalize_text(user_text)

    greetings = [
        "xin chao",
        "chao",
        "chao ban",
        "hello",
        "hi",
        "alo",
        "menu",
        "danh muc",
        "bat dau",
        "0",
    ]

    return text in greetings


def get_welcome_message():
    menu_rows = read_menu()

    lines = []

    for index, row in enumerate(menu_rows, start=1):
        title = (
            row.get("TEN_CHUC_NANG")
            or row.get("TEN")
            or row.get("CHU_DE")
            or row.get("MO_TA")
            or ""
        )

        title = str(title).strip()

        if title:
            lines.append(f"{index}. {title}")

    if not lines:
        lines = [
            "1. Làm căn cước",
            "2. Đăng ký cư trú",
            "3. VNeID / định danh điện tử",
            "4. Phản ánh ANTT",
            "5. Số điện thoại trực ban",
            "6. Gặp cán bộ trực",
        ]

    menu_text = "\n".join(lines)

    return (
        "🇻🇳 CHÀO MỪNG QUÝ CÔNG DÂN\n"
        "Đến với Trợ lý AI Công an phường Phù Liễn, thành phố Hải Phòng.\n\n"
        "📋 DANH MỤC HỖ TRỢ\n"
        f"{menu_text}\n\n"
        "💬 Quý công dân có thể nhập số thứ tự hoặc nhập trực tiếp nội dung cần hỏi."
    )


# =========================
# TRẢ LỜI TỪ MENU
# =========================

def answer_from_menu(menu_row):
    ten = (
        menu_row.get("TEN_CHUC_NANG")
        or menu_row.get("TEN")
        or menu_row.get("CHU_DE")
        or ""
    )

    mo_ta = menu_row.get("MO_TA", "")

    sheet = (
        menu_row.get("SHEET_DU_LIEU")
        or menu_row.get("SHEET")
        or ""
    )

    parts = []

    if ten:
        parts.append(f"📌 {ten}")

    if mo_ta:
        parts.append(str(mo_ta))

    if sheet:
        parts.append(
            f"Quý công dân vui lòng nhập nội dung cụ thể để tôi tra cứu trong nhóm: {sheet}"
        )

    return "\n\n".join(parts) if parts else get_welcome_message()


# =========================
# ROUTER CHÍNH
# =========================

def route_message(user_text):
    if not user_text or not str(user_text).strip():
        return DEFAULT_REPLY, "EMPTY"

    text = str(user_text).strip()

    # 1. Chào / menu
    if is_greeting(text):
        return get_welcome_message(), "WELCOME"

    # 2. Menu số hoặc từ khóa menu
    menu_result = search_menu(text)
    if menu_result:
        return answer_from_menu(menu_result), "MENU"

    # 3. Tra cứu liên hệ
    lien_he_results = search_lien_he(text, limit=3)
    if lien_he_results:
        reply = format_multiple_results(
            lien_he_results,
            format_lien_he,
            limit=3
        )
        return reply, "TRA_CUU_LIEN_HE"

    # 4. FAQ
    faq_results = search_faq(text, limit=3)
    if faq_results:
        reply = format_multiple_results(
            faq_results,
            format_faq,
            limit=3
        )
        return reply, "FAQ"

    # 5. Thủ tục hành chính
    thu_tuc_results = search_thu_tuc(text, limit=3)
    if thu_tuc_results:
        reply = format_multiple_results(
            thu_tuc_results,
            format_thu_tuc,
            limit=3
        )
        return reply, "THU_TUC"

    # 6. Không tìm thấy
    return DEFAULT_REPLY, "DEFAULT"


def route_message_for_ai(user_text):
    reply, source = route_message(user_text)

    use_ai = source in ["DEFAULT", "EMPTY"]

    return {
        "reply": reply,
        "source": source,
        "use_ai": use_ai,
    }
