from config import DEFAULT_REPLY
from services.sheet_api import read_menu, read_lien_he
from services.text_utils import normalize_text, get_first, safe_int, compact
from services.search_engine import (
    search_menu,
    search_lien_he,
    search_faq,
    search_thu_tuc,
    list_procedures_by_sheet,
    find_procedure_by_id,
    format_lien_he,
    format_faq,
    format_thu_tuc,
    format_multiple_results,
)


PAGE_SIZE = 5


def is_greeting(text):
    return normalize_text(text) in [
        "xin chao", "chao", "chao ban", "hello", "hi",
        "alo", "menu", "danh muc", "bat dau", "0"
    ]


def is_reset_question(text):
    t = normalize_text(text)
    return t in [
        "huy", "thoat", "lam lai", "menu chinh", "quay lai",
        "xoa", "reset", "xong", "xong roi", "da ro",
        "toi hieu roi", "duoc roi", "ok roi",
        "cam on", "cam on ban", "ok cam on",
        "cam on nhe", "cam on nhieu",
        "thank", "thanks", "thank you"
    ]


def is_next_page_question(text):
    return normalize_text(text) in [
        "xem tiep", "xem them", "tiep", "trang tiep", "next"
    ]


def get_end_message():
    return (
        "🙏 Cảm ơn Quý công dân đã sử dụng Trợ lý AI Công an phường Phù Liễn.\n\n"
        "Rất hân hạnh được hỗ trợ Quý công dân.\n\n"
        "Khi cần hỗ trợ thêm, Quý công dân chỉ cần nhắn:\n"
        "• menu\n"
        "hoặc nhập trực tiếp nội dung cần hỏi.\n\n"
        "Kính chúc Quý công dân sức khỏe và nhiều điều tốt đẹp!"
    )


def is_location_question(text):
    t = normalize_text(text)
    keys = [
        "o dau", "dia chi", "dia diem", "noi lam", "lam o dau",
        "nop o dau", "co quan tiep nhan", "tiep nhan",
        "noi tiep nhan", "co quan thuc hien", "noi thuc hien",
        "noi nop", "den dau", "den dau lam", "di dau lam",
        "toi dau lam", "lam cho nao", "nop cho nao",
        "den cho nao", "o cho nao", "bo phan nao",
        "vi tri", "ban do", "google map", "map"
    ]
    return any(k in t for k in keys)


def is_specific_contact_question(text):
    t = normalize_text(text)
    agency_keys = [
        "cong an phuong",
        "cong an thanh pho",
        "catp",
        "pc08",
        "pc07",
        "phong canh sat",
        "phong csgt",
        "phong pccc",
        "phong csqlhc",
        "so tu phap",
        "cuc c06",
        "c06",
        "bo cong an",
        "phu lien",
        "kien an",
    ]
    return is_location_question(t) and any(k in t for k in agency_keys)


def is_followup_detail_question(user_text):
    text = normalize_text(user_text)
    detail_keywords = [
        "ho so", "ho so chi tiet", "giay to", "can giay to gi", "can gi",
        "trinh tu", "quy trinh", "quy trinh thuc hien",
        "cac buoc", "buoc thuc hien", "thu tuc thuc hien",
        "co quan tiep nhan", "noi tiep nhan", "noi thuc hien",
        "noi nop", "nop o dau", "lam o dau", "dia diem",
        "o dau", "o cho nao", "den dau", "den dau lam", "di dau lam", "toi dau lam",
        "vi tri", "ban do", "google map", "map",
        "thoi han", "bao lau", "may ngay",
        "le phi", "phi", "mat phi", "co mat phi khong",
        "co so phap ly", "can cu phap ly",
        "link", "link dvc", "dich vu cong",
        "ket qua", "luu y", "chi tiet",
    ]
    return any(kw in text for kw in detail_keywords)


def find_lien_he_by_ten_co_quan(name):
    if not name:
        return None

    name_norm = normalize_text(name)
    rows = read_lien_he()

    for row in rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        if normalize_text(ten) == name_norm:
            return row

    for row in rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        ten_norm = normalize_text(ten)
        if name_norm in ten_norm or ten_norm in name_norm:
            return row

    return None


def get_welcome_message():
    rows = read_menu()
    lines = []

    for i, row in enumerate(rows, start=1):
        title = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE", "MO_TA", "MÔ_TẢ")
        if title:
            lines.append(f"{i}. {title}")

    if not lines:
        lines = [
            "1. Căn cước",
            "2. Cư trú",
            "3. VNeID / định danh điện tử",
            "4. Phản ánh ANTT",
            "5. Số điện thoại trực ban",
            "6. Gặp cán bộ trực",
        ]

    return (
        "🇻🇳 CHÀO MỪNG QUÝ CÔNG DÂN\n"
        "Đến với Trợ lý AI Công an phường Phù Liễn, thành phố Hải Phòng.\n\n"
        "📋 DANH MỤC HỖ TRỢ\n"
        + "\n".join(lines)
        + "\n\n💬 Quý công dân có thể nhập số thứ tự hoặc nhập trực tiếp nội dung cần hỏi."
    )


def menu_context(row):
    return {
        "sheet": get_first(row, "SHEET_DU_LIEU", "SHEET"),
        "topic": get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE"),
        "stage": "procedure_list",
        "procedure_id": "",
        "procedure_name": "",
        "page": 1,
        "last_suggestions": [],
    }


def _make_procedure_list_reply(sheet, topic="", page=1):
    if not sheet or not sheet.startswith("THU_TUC_"):
        return None

    all_rows = list_procedures_by_sheet(sheet, limit=999)
    if not all_rows:
        return None

    page = max(safe_int(page, default=1), 1)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_rows = all_rows[start:end]

    if not page_rows:
        last_page = max(((len(all_rows) - 1) // PAGE_SIZE) + 1, 1)
        page = last_page
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        page_rows = all_rows[start:end]

    suggestions = []
    lines = []
    for i, row in enumerate(page_rows, start=1):
        name = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
        pid = get_first(row, "ID")
        suggestions.append({"index": i, "id": pid, "name": name})
        if name:
            lines.append(f"{i}. {name}")

    title = topic or sheet.replace("THU_TUC_", "")
    total = len(all_rows)
    has_next = end < total

    reply_parts = [
        f"📌 {title}",
        "Quý công dân vui lòng chọn thủ tục:",
        "\n".join(lines),
        "Nhắn số thứ tự để chọn thủ tục hoặc nhập từ khóa gần đúng của thủ tục cần hỏi.",
    ]

    if has_next:
        reply_parts.append("Nhắn \"xem tiếp\" để xem thêm thủ tục.")
    else:
        reply_parts.append("Đã hiển thị hết danh sách thủ tục trong nhóm này.")

    new_ctx = {
        "sheet": sheet,
        "topic": title,
        "stage": "procedure_list",
        "procedure_id": "",
        "procedure_name": "",
        "page": page,
        "last_suggestions": suggestions,
    }

    return "\n\n".join(reply_parts), new_ctx


def answer_from_menu(row):
    title = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE")
    desc = get_first(row, "MO_TA", "MÔ_TẢ")
    sheet = get_first(row, "SHEET_DU_LIEU", "SHEET")

    if sheet and sheet.startswith("THU_TUC_"):
        grouped = _make_procedure_list_reply(sheet, topic=title, page=1)
        if grouped:
            reply, new_ctx = grouped
            if desc:
                reply = reply.replace(
                    f"📌 {title}\n\n",
                    f"📌 {title}\n\n{desc}\n\n",
                    1
                )
            return reply, new_ctx.get("last_suggestions", [])

    parts = []
    if title:
        parts.append(f"📌 {title}")
    if desc:
        parts.append(str(desc))
    if sheet:
        parts.append(f"Quý công dân vui lòng nhập nội dung cụ thể để tôi tra cứu trong nhóm: {sheet}")

    return ("\n\n".join(parts) if parts else get_welcome_message()), []


def detect_explicit_topic(text):
    t = normalize_text(text)

    topic_map = {
        "THU_TUC_CCCD": [
            "can cuoc", "cccd", "the can cuoc", "lam can cuoc", "cap can cuoc"
        ],
        "THU_TUC_CUTRU": [
            "cu tru", "tam tru", "thuong tru", "tam vang", "luu tru",
            "xac nhan cu tru", "tach ho"
        ],
        "THU_TUC_VNEID": [
            "vneid", "dinh danh", "muc 2", "kich hoat vneid"
        ],
        "THU_TUC_PTGT": [
            "dang ky xe", "bien so", "sang ten xe", "phuong tien", "xe may", "o to"
        ],
        "THU_TUC_PCCC": [
            "pccc", "phong chay", "chua chay", "nghiem thu pccc", "tham duyet pccc"
        ],
        "THU_TUC_VKVLN": [
            "vu khi", "vat lieu no", "cong cu ho tro", "phao"
        ],
        "THU_TUC_LLTP": [
            "ly lich tu phap", "phieu ly lich", "lltp"
        ],
        "THU_TUC_ANTT": [
            "nganh nghe", "antt", "kinh doanh co dieu kien",
            "karaoke", "cam do", "dich vu bao ve"
        ],
    }

    for sheet, keys in topic_map.items():
        if any(k in t for k in keys):
            return {
                "sheet": sheet,
                "topic": sheet.replace("THU_TUC_", ""),
                "stage": "procedure_list",
            }

    return None


def context_prefix(ctx):
    sheet = ctx.get("sheet", "")
    mapping = {
        "THU_TUC_CCCD": "căn cước ",
        "THU_TUC_CUTRU": "cư trú ",
        "THU_TUC_VNEID": "vneid ",
        "THU_TUC_PTGT": "đăng ký xe ",
        "THU_TUC_PCCC": "pccc ",
        "THU_TUC_VKVLN": "vũ khí vật liệu nổ công cụ hỗ trợ ",
        "THU_TUC_LLTP": "lý lịch tư pháp ",
        "THU_TUC_ANTT": "ngành nghề antt ",
    }
    return mapping.get(sheet, "")


def answer_procedure_detail(row, user_text):
    t = normalize_text(user_text)
    ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")

    if "ho so" in t or "giay to" in t or "can gi" in t or "chi tiet" in t:
        value = get_first(row, "HO_SO", "HỒ_SƠ", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")
        return f"📄 Hồ sơ - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)

    if (
        "trinh tu" in t
        or "quy trinh" in t
        or "quy trinh thuc hien" in t
        or "cac buoc" in t
        or "buoc thuc hien" in t
        or "thu tuc thuc hien" in t
    ):
        value = get_first(row, "TRINH_TU", "TRÌNH_TỰ", "QUY_TRINH", "QUY_TRÌNH")
        return f"📝 Trình tự thực hiện - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)

    if is_location_question(t):
        co_quan = get_first(
            row,
            "CO_QUAN_THUC_HIEN",
            "CƠ_QUAN_THỰC_HIỆN",
            "CO_QUAN_TIEP_NHAN",
            "CƠ_QUAN_TIẾP_NHẬN",
            "NOI_NOP",
            "NƠI_NỘP",
            "NOI_THUC_HIEN",
            "NƠI_THỰC_HIỆN",
        )

        lien_he = find_lien_he_by_ten_co_quan(co_quan)
        if lien_he:
            return format_lien_he(lien_he)

        if co_quan:
            return f"📍 Cơ quan/nơi tiếp nhận - {ten}\n\n{compact(co_quan, 1800)}"

        return (
            f"📍 Cơ quan/nơi tiếp nhận - {ten}\n\n"
            "Quý công dân vui lòng liên hệ Công an phường để được hướng dẫn cụ thể."
        )

    if "bao lau" in t or "thoi han" in t:
        value = get_first(row, "THOI_HAN", "THỜI_HẠN")
        return f"⏱ Thời hạn - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "le phi" in t or "mat phi" in t or t == "phi":
        value = get_first(row, "LE_PHI", "LỆ_PHÍ", "PHI")
        return f"💰 Lệ phí - {ten}\n\n{value}" if value else format_thu_tuc(row)

    if "ket qua" in t:
        value = get_first(row, "KET_QUA", "KẾT_QUẢ")
        return f"✅ Kết quả - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)

    if "co so phap ly" in t:
        value = get_first(row, "CO_SO_PHAP_LY", "CƠ_SỞ_PHÁP_LÝ")
        return f"⚖️ Cơ sở pháp lý - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)

    if "luu y" in t:
        value = get_first(row, "LUU_Y", "LƯU_Ý")
        return f"ℹ️ Lưu ý - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)

    if "link" in t or "dich vu cong" in t:
        value = get_first(row, "LINK_DVC", "LINK")
        return f"🔗 Link dịch vụ công - {ten}\n\n{value}" if value else format_thu_tuc(row)

    return format_thu_tuc(row)


def build_ai_context(ctx):
    parts = []

    if ctx.get("procedure_id"):
        p = find_procedure_by_id(ctx.get("procedure_id"))
        if p:
            parts.append(format_thu_tuc(p))

    elif ctx.get("sheet"):
        rows = list_procedures_by_sheet(ctx.get("sheet"), limit=5)
        if rows:
            names = [
                get_first(r, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
                for r in rows
                if get_first(r, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
            ]
            parts.append("Các thủ tục liên quan:\n" + "\n".join(names))

    return "\n\n".join(parts)


def _select_from_suggestions(text, ctx):
    t = normalize_text(text)
    if not t.isdigit():
        return None

    idx = safe_int(t, default=-1)
    for item in ctx.get("last_suggestions", []) or []:
        if int(item.get("index", -99)) == idx:
            return find_procedure_by_id(item.get("id"))

    return None


def _find_procedure_in_current_sheet(text, ctx):
    sheet = ctx.get("sheet", "")
    if not sheet or not sheet.startswith("THU_TUC_"):
        return None

    results = search_thu_tuc(text, limit=5, sheet=sheet)
    if not results:
        return None

    best = results[0]
    best_score = best.get("_SCORE", 0)
    second_score = results[1].get("_SCORE", 0) if len(results) > 1 else 0

    if best_score >= 20 and best_score >= second_score + 8:
        return best

    return None


def _procedure_list_reply_for_context(ctx):
    sheet = ctx.get("sheet", "")
    topic = ctx.get("topic", "")
    page = ctx.get("page", 1)
    return _make_procedure_list_reply(sheet, topic=topic, page=page)


def _need_select_procedure_message(ctx):
    grouped = _procedure_list_reply_for_context(ctx)
    if grouped:
        reply, new_ctx = grouped
        reply = (
            "Tôi chưa xác định được thủ tục cần chọn trong nhóm này.\n\n"
            + reply
        )
        return reply, new_ctx

    return (
        "Tôi chưa xác định được thủ tục cần chọn. Quý công dân vui lòng nhập 'menu' để xem danh mục hỗ trợ.",
        ctx
    )


def route_message(user_text, context=None):
    ctx = dict(context or {})
    text = str(user_text or "").strip()
    text_norm = normalize_text(text)

    if not text:
        return DEFAULT_REPLY, "EMPTY", ctx, ""

    if is_reset_question(text):
        return get_end_message(), "RESET", {}, ""

    if is_greeting(text):
        return get_welcome_message(), "WELCOME", {}, ""

    # Câu hỏi rõ tên cơ quan: bỏ ngữ cảnh thủ tục cũ
    if is_specific_contact_question(text):
        lien_he = search_lien_he(text, limit=3)
        if lien_he:
            return format_multiple_results(lien_he, format_lien_he, limit=3), "TRA_CUU_LIEN_HE_EXPLICIT", {}, ""

    # Chọn số trong danh sách thủ tục đang hiển thị
    selected = _select_from_suggestions(text, ctx)
    if selected:
        new_ctx = {
            "sheet": selected.get("_SHEET", ctx.get("sheet", "")),
            "topic": get_first(selected, "CHU_DE", "CHỦ_ĐỀ", default=ctx.get("topic", "")),
            "procedure_id": get_first(selected, "ID"),
            "procedure_name": get_first(selected, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
            "stage": "procedure",
            "page": ctx.get("page", 1),
            "last_suggestions": [],
        }
        return format_thu_tuc(selected), "THU_TUC_SELECT", new_ctx, ""

    # Khi đang ở nhóm thủ tục, số thứ tự phải ưu tiên danh sách đang hiển thị.
    # Nếu không có số đó trong last_suggestions thì nhắc chọn lại, không chuyển sang menu.
    if text_norm.isdigit() and ctx.get("sheet", "").startswith("THU_TUC_") and not ctx.get("procedure_id"):
        reply, new_ctx = _need_select_procedure_message(ctx)
        return reply, "NEED_PROCEDURE_SELECT", new_ctx, ""

    # Chọn menu chính bằng số
    if text_norm.isdigit():
        menu = search_menu(text)
        if menu:
            reply, suggestions = answer_from_menu(menu)
            new_ctx = menu_context(menu)
            new_ctx["last_suggestions"] = suggestions
            new_ctx["stage"] = "procedure_list"
            new_ctx["page"] = 1
            return reply, "MENU", new_ctx, ""

    # Có thủ tục hiện tại: ưu tiên hỏi tiếp theo ngữ cảnh
    if ctx.get("procedure_id") and is_followup_detail_question(text):
        procedure = find_procedure_by_id(ctx.get("procedure_id"))
        if procedure:
            return answer_procedure_detail(procedure, text), "PROCEDURE_CONTEXT", ctx, ""

    # Đang ở nhóm thủ tục: xử lý xem tiếp / nhập từ khóa trong đúng sheet hiện tại
    if ctx.get("sheet", "").startswith("THU_TUC_") and not ctx.get("procedure_id"):
        if is_next_page_question(text):
            next_ctx = dict(ctx)
            next_ctx["page"] = safe_int(ctx.get("page", 1), default=1) + 1
            grouped = _procedure_list_reply_for_context(next_ctx)
            if grouped:
                reply, new_ctx = grouped
                if new_ctx.get("page") == ctx.get("page"):
                    return (
                        "Đã hiển thị hết danh sách thủ tục trong nhóm này.\n"
                        "Quý công dân vui lòng nhắn số thứ tự hoặc nhập từ khóa gần đúng để chọn thủ tục.",
                        "END_PROCEDURE_LIST",
                        new_ctx,
                        ""
                    )
                return reply, "NEXT_PROCEDURE_PAGE", new_ctx, ""

        found = _find_procedure_in_current_sheet(text, ctx)
        if found:
            new_ctx = {
                "sheet": found.get("_SHEET", ctx.get("sheet", "")),
                "topic": get_first(found, "CHU_DE", "CHỦ_ĐỀ", default=ctx.get("topic", "")),
                "procedure_id": get_first(found, "ID"),
                "procedure_name": get_first(found, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                "stage": "procedure",
                "page": ctx.get("page", 1),
                "last_suggestions": [],
            }
            return format_thu_tuc(found), "THU_TUC_IN_GROUP", new_ctx, ""

        # Nếu đang ở nhóm mà hỏi chi tiết khi chưa chọn thủ tục, phải yêu cầu chọn thủ tục.
        # Không được rơi sang FAQ / liên hệ / toàn bộ hệ thống.
        reply, new_ctx = _need_select_procedure_message(ctx)
        return reply, "NEED_PROCEDURE_SELECT", new_ctx, ""

    explicit = detect_explicit_topic(text)

    if explicit:
        grouped = _make_procedure_list_reply(
            explicit.get("sheet", ""),
            topic=explicit.get("topic", ""),
            page=1
        )
        if grouped:
            reply, new_ctx = grouped
            return reply, "MENU_GROUP", new_ctx, ""

    # Không có ngữ cảnh + câu hỏi địa điểm quá mơ hồ
    if (
        not ctx.get("procedure_id")
        and not explicit
        and is_location_question(text)
        and not is_specific_contact_question(text)
    ):
        lien_he = search_lien_he(text, limit=3)

        if lien_he and text_norm not in [
            "o dau", "lam o dau", "den dau", "den dau lam",
            "di dau lam", "toi dau lam", "vi tri", "map", "google map"
        ]:
            return format_multiple_results(lien_he, format_lien_he, limit=3), "TRA_CUU_LIEN_HE", {}, ""

        return (
            "Quý công dân vui lòng nêu rõ nội dung cần hỗ trợ.\n\n"
            "Ví dụ:\n"
            "• Làm căn cước ở đâu\n"
            "• Đăng ký tạm trú ở đâu\n"
            "• Công an phường Phù Liễn ở đâu\n\n"
            "Hoặc nhập 'menu' để xem danh mục hỗ trợ.",
            "ASK_TOPIC",
            {},
            ""
        )

    menu_keys = [
        "can cuoc", "cu tru", "vneid", "phuong tien giao thong",
        "dang ky xe", "ly lich tu phap", "pccc", "vkvln",
        "lien he", "tra cuu lien he"
    ]

    if text_norm in menu_keys:
        menu = search_menu(text)
        if menu:
            reply, suggestions = answer_from_menu(menu)
            new_ctx = menu_context(menu)
            new_ctx["last_suggestions"] = suggestions
            new_ctx["stage"] = "procedure_list"
            new_ctx["page"] = 1
            return reply, "MENU", new_ctx, ""

    search_text = text

    thu_tuc_results = search_thu_tuc(search_text, limit=5, sheet=None)

    if thu_tuc_results:
        best = thu_tuc_results[0]
        best_score = best.get("_SCORE", 0)
        second_score = thu_tuc_results[1].get("_SCORE", 0) if len(thu_tuc_results) > 1 else 0

        if best_score >= 20 and best_score >= second_score + 8:
            new_ctx = {
                "sheet": best.get("_SHEET", ""),
                "topic": get_first(best, "CHU_DE", "CHỦ_ĐỀ"),
                "procedure_id": get_first(best, "ID"),
                "procedure_name": get_first(best, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                "stage": "procedure",
                "page": 1,
                "last_suggestions": [],
            }
            return format_thu_tuc(best), "THU_TUC", new_ctx, ""

        # Nếu có nhiều thủ tục gần giống trên toàn hệ thống thì yêu cầu chọn số
        suggestions = []
        lines = []
        for i, row in enumerate(thu_tuc_results[:5], start=1):
            name = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
            pid = get_first(row, "ID")
            suggestions.append({"index": i, "id": pid, "name": name})
            if name:
                lines.append(f"{i}. {name}")

        ctx["last_suggestions"] = suggestions
        ctx["stage"] = "clarify_global"
        return (
            "Tôi tìm thấy một số thủ tục gần giống nhau. "
            "Quý công dân vui lòng chọn số tương ứng:\n\n"
            + "\n".join(lines),
            "CLARIFY_THU_TUC",
            ctx,
            ""
        )

    # Chỉ tra cứu liên hệ khi câu hỏi có ý định liên hệ/địa điểm rõ ràng
    if is_location_question(text) or text_norm in [
        "lien he",
        "so dien thoai",
        "truc ban",
        "google map",
        "ban do",
    ]:
        lien_he = search_lien_he(search_text, limit=3)
        if lien_he:
            return format_multiple_results(lien_he, format_lien_he, limit=3), "TRA_CUU_LIEN_HE", ctx, ""

    # Chỉ tìm FAQ khi câu hỏi có vẻ thuộc phạm vi hỗ trợ
    if (
        ctx.get("procedure_id")
        or is_location_question(text)
        or text_norm in [
            "lien he",
            "so dien thoai",
            "truc ban",
            "google map",
            "ban do",
            "menu",
        ]
    ):
        faq = search_faq(search_text, limit=3)
        if faq:
            return format_multiple_results(faq, format_faq, limit=3), "FAQ", ctx, ""

    return DEFAULT_REPLY, "DEFAULT", ctx, build_ai_context(ctx)


def route_message_for_ai(user_text, context=None):
    reply, source, new_context, ai_context = route_message(user_text, context=context)

    return {
        "reply": reply,
        "source": source,
        "use_ai": source in ["DEFAULT", "EMPTY"],
        "context": new_context,
        "ai_context": ai_context,
    }
