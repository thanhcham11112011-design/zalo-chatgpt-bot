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

    return (
        "🇻🇳 CHÀO MỪNG QUÝ CÔNG DÂN\n"
        "Đến với Trợ lý AI Công an phường Phù Liễn, thành phố Hải Phòng.\n\n"
        "📋 DANH MỤC HỖ TRỢ\n"
        f"{chr(10).join(lines)}\n\n"
        "💬 Quý công dân có thể nhập số thứ tự hoặc nhập trực tiếp nội dung cần hỏi."
    )


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


def search_menu_strict(user_text):
    """
    MENU chỉ bắt khi:
    - Người dân nhập đúng ID menu, ví dụ: 1, 2, 3
    - Hoặc nhập đúng tên chức năng, ví dụ: căn cước, cư trú, vneid
    Không bắt theo TU_KHOA để tránh đè lên THU_TUC.
    """
    text_norm = normalize_text(user_text)
    menu_rows = read_menu()

    for row in menu_rows:
        menu_id = str(row.get("ID", "")).strip()

        ten_chuc_nang = (
            row.get("TEN_CHUC_NANG")
            or row.get("TEN")
            or row.get("CHU_DE")
            or ""
        )

        if text_norm == normalize_text(menu_id):
            return row

        if text_norm == normalize_text(ten_chuc_nang):
            return row

    return None

def detect_explicit_topic(user_text):
    text = normalize_text(user_text)

    topic_map = {
        "THU_TUC_CCCD": ["can cuoc", "cccd", "the can cuoc", "lam can cuoc", "cap can cuoc"],
        "THU_TUC_CUTRU": ["cu tru", "tam tru", "thuong tru", "tam vang", "luu tru"],
        "THU_TUC_VNEID": ["vneid", "dinh danh", "muc 2"],
        "THU_TUC_PTGT": ["dang ky xe", "bien so", "sang ten xe", "phuong tien"],
        "THU_TUC_PCCC": ["pccc", "phong chay", "chua chay"],
        "THU_TUC_VKVLN": ["vu khi", "vat lieu no", "cong cu ho tro", "phao"],
        "THU_TUC_LLTP": ["ly lich tu phap", "phieu ly lich"],
        "THU_TUC_ANTT": ["nganh nghe", "antt", "kinh doanh co dieu kien"],
    }

    for sheet, keywords in topic_map.items():
        for kw in keywords:
            if kw in text:
                return {
                    "sheet": sheet,
                    "topic": sheet.replace("THU_TUC_", "")
                }

    return None

def route_message(user_text, context=None):
    context = context or {}

    if not user_text or not str(user_text).strip():
        return DEFAULT_REPLY, "EMPTY", context

    text = str(user_text).strip()
    text_norm = normalize_text(text)

    # 1. Chào / menu
    if is_greeting(text):
        return get_welcome_message(), "WELCOME", {}

    # 2. Ưu tiên tuyệt đối nếu người dân nhập số menu
    if text_norm.isdigit():
        menu_result = search_menu(text)

        if menu_result:
            sheet = (
                menu_result.get("SHEET_DU_LIEU")
                or menu_result.get("SHEET")
                or ""
            )

            new_context = {
                "sheet": sheet,
                "topic": menu_result.get("TEN_CHUC_NANG")
                or menu_result.get("TEN")
                or menu_result.get("CHU_DE")
                or ""
            }

            return answer_from_menu(menu_result), "MENU", new_context

    # 3. Nếu người dân hỏi rõ sang lĩnh vực mới thì đổi context
    explicit_context = detect_explicit_topic(text)

    if explicit_context:
        context = explicit_context
    else:
        # 4. Chỉ dùng context cũ khi câu hỏi ngắn/mơ hồ
        if context.get("sheet") == "THU_TUC_CCCD":
            text = "căn cước " + text
        elif context.get("sheet") == "THU_TUC_CUTRU":
            text = "cư trú " + text
        elif context.get("sheet") == "THU_TUC_VNEID":
            text = "vneid " + text
        elif context.get("sheet") == "THU_TUC_PTGT":
            text = "đăng ký xe " + text
        elif context.get("sheet") == "THU_TUC_PCCC":
            text = "pccc " + text
        elif context.get("sheet") == "THU_TUC_VKVLN":
            text = "vũ khí công cụ hỗ trợ " + text
        elif context.get("sheet") == "THU_TUC_LLTP":
            text = "lý lịch tư pháp " + text
        elif context.get("sheet") == "THU_TUC_ANTT":
            text = "ngành nghề antt " + text

    # 5. Menu tên nhóm ngắn
    menu_keywords = [
        "can cuoc",
        "cu tru",
        "vneid",
        "phuong tien giao thong",
        "ly lich tu phap",
        "nganh nghe dau tu kinh doanh co dieu kien ve antt",
        "phong chay chua chay",
        "pccc",
        "vu khi vat lieu no cong cu ho tro",
        "vkvln",
        "tra cuu lien he",
        "lien he",
    ]

    if text_norm in menu_keywords:
        menu_result = search_menu(text)

        if menu_result:
            sheet = (
                menu_result.get("SHEET_DU_LIEU")
                or menu_result.get("SHEET")
                or ""
            )

            new_context = {
                "sheet": sheet,
                "topic": menu_result.get("TEN_CHUC_NANG")
                or menu_result.get("TEN")
                or menu_result.get("CHU_DE")
                or ""
            }

            return answer_from_menu(menu_result), "MENU", new_context

    # 6. Ưu tiên tìm thủ tục trước FAQ
    thu_tuc_results = search_thu_tuc(text, limit=3)
    if thu_tuc_results:
        reply = format_multiple_results(
            thu_tuc_results,
            format_thu_tuc,
            limit=3
        )
        return reply, "THU_TUC", context

    # 7. Tra cứu liên hệ
    lien_he_results = search_lien_he(text, limit=3)
    if lien_he_results:
        reply = format_multiple_results(
            lien_he_results,
            format_lien_he,
            limit=3
        )
        return reply, "TRA_CUU_LIEN_HE", context

    # 8. FAQ
    faq_results = search_faq(text, limit=3)
    if faq_results:
        reply = format_multiple_results(
            faq_results,
            format_faq,
            limit=3
        )
        return reply, "FAQ", context

    # 9. Không tìm thấy
    return DEFAULT_REPLY, "DEFAULT", context

def route_message_for_ai(user_text, context=None):
    context = context or {}

    reply, source, new_context = route_message(
        user_text,
        context=context
    )

    use_ai = source in ["DEFAULT", "EMPTY"]

    return {
        "reply": reply,
        "source": source,
        "use_ai": use_ai,
        "context": new_context,
    }
