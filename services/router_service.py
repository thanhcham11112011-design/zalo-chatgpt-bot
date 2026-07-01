# services/router_service.py
# Điều hướng câu hỏi người dân sang đúng nguồn dữ liệu

from config import DEFAULT_REPLY
from services.sheet_api import read_menu, read_all_thu_tuc

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
# MENU
# =========================

def answer_from_menu(menu_row):
    ten = (
        menu_row.get("TEN_CHUC_NANG")
        or menu_row.get("TEN")
        or menu_row.get("CHU_DE")
        or ""
    )
    mo_ta = menu_row.get("MO_TA", "")
    sheet = menu_row.get("SHEET_DU_LIEU") or menu_row.get("SHEET") or ""

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


def build_menu_context(menu_row):
    return {
        "sheet": menu_row.get("SHEET_DU_LIEU") or menu_row.get("SHEET") or "",
        "topic": (
            menu_row.get("TEN_CHUC_NANG")
            or menu_row.get("TEN")
            or menu_row.get("CHU_DE")
            or ""
        ),
    }


# =========================
# NHẬN DIỆN LĨNH VỰC RÕ RÀNG
# =========================

def detect_explicit_topic(user_text):
    text = normalize_text(user_text)

    topic_map = {
        "THU_TUC_CCCD": [
            "can cuoc",
            "cccd",
            "the can cuoc",
            "lam can cuoc",
            "cap can cuoc",
        ],
        "THU_TUC_CUTRU": [
            "cu tru",
            "tam tru",
            "thuong tru",
            "tam vang",
            "luu tru",
            "xac nhan cu tru",
            "tach ho",
        ],
        "THU_TUC_VNEID": [
            "vneid",
            "dinh danh",
            "muc 2",
            "kich hoat vneid",
        ],
        "THU_TUC_PTGT": [
            "dang ky xe",
            "bien so",
            "sang ten xe",
            "phuong tien",
            "xe may",
            "o to",
        ],
        "THU_TUC_PCCC": [
            "pccc",
            "phong chay",
            "chua chay",
            "nghiem thu pccc",
            "tham duyet pccc",
        ],
        "THU_TUC_VKVLN": [
            "vu khi",
            "vat lieu no",
            "cong cu ho tro",
            "phao",
        ],
        "THU_TUC_LLTP": [
            "ly lich tu phap",
            "phieu ly lich",
            "lltp",
        ],
        "THU_TUC_ANTT": [
            "nganh nghe",
            "antt",
            "kinh doanh co dieu kien",
            "karaoke",
            "cam do",
            "luu tru",
            "dich vu bao ve",
        ],
    }

    for sheet, keywords in topic_map.items():
        for kw in keywords:
            if kw in text:
                return {
                    "sheet": sheet,
                    "topic": sheet.replace("THU_TUC_", ""),
                }

    return None


# =========================
# PROCEDURE CONTEXT
# =========================

def is_followup_detail_question(user_text):
    text = normalize_text(user_text)

    detail_keywords = [
        "ho so",
        "can giay to gi",
        "can gi",
        "giay to",
        "thu tuc gom gi",
        "trinh tu",
        "cac buoc",
        "lam o dau",
        "nop o dau",
        "noi thuc hien",
        "noi nop",
        "co quan thuc hien",
        "bao lau",
        "thoi han",
        "le phi",
        "phi",
        "mat phi khong",
        "ket qua",
        "co so phap ly",
        "luu y",
        "link",
        "dich vu cong",
    ]

    return any(kw in text for kw in detail_keywords)


def find_procedure_by_id(procedure_id):
    if not procedure_id:
        return None

    rows = read_all_thu_tuc()
    procedure_id = str(procedure_id).strip()

    for row in rows:
        if str(row.get("ID", "")).strip() == procedure_id:
            return row

    return None


def answer_procedure_detail(row, user_text):
    text = normalize_text(user_text)

    ten = row.get("TEN_THU_TUC", "")

    if "ho so" in text or "giay to" in text or "can gi" in text:
        value = row.get("HO_SO") or row.get("TRA_LOI_DAY_DU") or ""
        return f"📄 Hồ sơ - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "trinh tu" in text or "cac buoc" in text:
        value = row.get("TRINH_TU") or ""
        return f"📝 Trình tự thực hiện - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if (
        "lam o dau" in text
        or "nop o dau" in text
        or "noi thuc hien" in text
        or "noi nop" in text
        or "co quan thuc hien" in text
    ):
        value = (
            row.get("CO_QUAN_THUC_HIEN")
            or row.get("NOI_NOP")
            or row.get("LUU_Y")
            or ""
        )
        return f"📍 Nơi thực hiện - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "bao lau" in text or "thoi han" in text:
        value = row.get("THOI_HAN") or ""
        return f"⏱ Thời hạn - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "le phi" in text or "mat phi" in text or text == "phi":
        value = row.get("LE_PHI") or row.get("PHI") or ""
        return f"💰 Lệ phí - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "ket qua" in text:
        value = row.get("KET_QUA") or ""
        return f"✅ Kết quả - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "co so phap ly" in text:
        value = row.get("CO_SO_PHAP_LY") or ""
        return f"⚖️ Cơ sở pháp lý - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "luu y" in text:
        value = row.get("LUU_Y") or ""
        return f"ℹ️ Lưu ý - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "link" in text or "dich vu cong" in text:
        value = row.get("LINK_DVC") or ""
        return f"🔗 Link dịch vụ công - {ten}\n\n{value}" if value else format_thu_tuc(row)

    return format_thu_tuc(row)


# =========================
# ROUTER CHÍNH
# =========================
def is_location_question(user_text):
    text = normalize_text(user_text)

    keywords = [
        "noi thuc hien",
        "lam o dau",
        "nop o dau",
        "o dau",
        "co quan thuc hien",
        "dia chi",
        "lien he",
        "google map",
        "ban do",
    ]

    return any(kw in text for kw in keywords)

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
            return answer_from_menu(menu_result), "MENU", build_menu_context(menu_result)

    # 3. Nếu đang có thủ tục cụ thể và người dân hỏi tiếp chi tiết
    if context.get("procedure_id") and is_followup_detail_question(text):
    procedure = find_procedure_by_id(context.get("procedure_id"))

    if procedure:
        if is_location_question(text):
            co_quan = (
                procedure.get("CO_QUAN_THUC_HIEN")
                or procedure.get("NOI_NOP")
                or procedure.get("NOI_THUC_HIEN")
                or ""
            )

            search_text = f"{co_quan} {procedure.get('CHU_DE', '')} {procedure.get('TEN_THU_TUC', '')}"
            lien_he_results = search_lien_he(search_text, limit=1)

            if lien_he_results:
                reply = format_multiple_results(
                    lien_he_results,
                    format_lien_he,
                    limit=1
                )
                return reply, "TRA_CUU_LIEN_HE_CONTEXT", context

        reply = answer_procedure_detail(procedure, text)
        return reply, "PROCEDURE_CONTEXT", context

    # 4. Nếu người dân hỏi rõ sang lĩnh vực mới thì đổi context
    explicit_context = detect_explicit_topic(text)

    if explicit_context:
        context = explicit_context
    else:
        # 5. Chỉ dùng context cũ khi câu hỏi ngắn/mơ hồ
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

    # 6. Menu tên nhóm ngắn
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
            return answer_from_menu(menu_result), "MENU", build_menu_context(menu_result)

    # 7. Ưu tiên tìm thủ tục trước FAQ
    thu_tuc_results = search_thu_tuc(text, limit=3)

    if thu_tuc_results:
        best = thu_tuc_results[0]
        best_score = best.get("_SCORE", 0)
        second_score = thu_tuc_results[1].get("_SCORE", 0) if len(thu_tuc_results) > 1 else 0

        # Nếu kết quả đầu đủ rõ ràng thì trả 01 thủ tục duy nhất
        if best_score >= 20 and best_score >= second_score + 8:
            reply = format_thu_tuc(best)

            new_context = {
                "sheet": best.get("_SHEET", context.get("sheet", "")),
                "topic": best.get("CHU_DE", context.get("topic", "")),
                "procedure_id": best.get("ID", ""),
                "procedure_name": best.get("TEN_THU_TUC", ""),
            }

            return reply, "THU_TUC", new_context

        # Nếu chưa rõ thì hỏi lại, không trả Top 3 thủ tục đầy đủ
        suggestions = []
        for index, row in enumerate(thu_tuc_results[:3], start=1):
            ten = row.get("TEN_THU_TUC", "")
            if ten:
                suggestions.append(f"{index}. {ten}")

        if suggestions:
            reply = (
                "Tôi tìm thấy một số thủ tục gần giống nhau. "
                "Quý công dân vui lòng nói rõ hơn cần thực hiện thủ tục nào:\n\n"
                + "\n".join(suggestions)
            )
            return reply, "CLARIFY_THU_TUC", context

    # 8. Tra cứu liên hệ
    lien_he_results = search_lien_he(text, limit=3)
    if lien_he_results:
        reply = format_multiple_results(lien_he_results, format_lien_he, limit=3)
        return reply, "TRA_CUU_LIEN_HE", context

    # 9. FAQ
    faq_results = search_faq(text, limit=3)
    if faq_results:
        reply = format_multiple_results(faq_results, format_faq, limit=3)
        return reply, "FAQ", context

    # 10. Không tìm thấy
    return DEFAULT_REPLY, "DEFAULT", context


def route_message_for_ai(user_text, context=None):
    context = context or {}

    reply, source, new_context = route_message(user_text, context=context)
    use_ai = source in ["DEFAULT", "EMPTY"]

    return {
        "reply": reply,
        "source": source,
        "use_ai": use_ai,
        "context": new_context,
    }
