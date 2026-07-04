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


# Chức năng: Kiểm tra tin nhắn có phải lời chào, yêu cầu menu hoặc bắt đầu lại hay không.
# Vai trò: Giúp BOT hiển thị menu chính khi người dân bắt đầu phiên chat.
def is_greeting(text):
    return normalize_text(text) in [
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
        "ket noi bot cap",
        "#ket noi bot cap",
        "ket_noi_bot_cap",
        "#ket_noi_bot_cap",
    ]


# Chức năng: Kiểm tra người dân có muốn kết thúc, hủy hoặc quay lại menu chính hay không.
# Đầu vào: text - nội dung người dân gửi.
# Đầu ra: True nếu là câu kết thúc/reset; False nếu không phải.
# Vai trò: Giúp BOT xóa context cũ và trả lời thông điệp kết thúc lịch sự.
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


# Chức năng: Kiểm tra người dân có yêu cầu xem tiếp danh sách thủ tục hay không.
# Đầu vào: text - nội dung người dân gửi.
# Đầu ra: True nếu là yêu cầu xem tiếp; False nếu không phải.
# Vai trò: Hỗ trợ phân trang danh sách thủ tục trong các sheet THU_TUC_*.
def is_next_page_question(text):
    return normalize_text(text) in [
        "xem tiep", "xem them", "tiep", "trang tiep", "next"
    ]


# Chức năng: Tạo thông điệp kết thúc phiên hỗ trợ.
# Đầu vào: Không có.
# Đầu ra: Chuỗi tin nhắn cảm ơn/kết thúc.
# Vai trò: Dùng khi người dân nhắn cảm ơn, xong, thoát hoặc reset.
def get_end_message():
    return (
        "🙏 Cảm ơn Quý công dân đã sử dụng Trợ lý AI Công an phường Phù Liễn.\n\n"
        "Rất hân hạnh được hỗ trợ Quý công dân.\n\n"
        "Khi cần hỗ trợ thêm, Quý công dân chỉ cần nhắn:\n"
        "• menu\n"
        "hoặc nhập trực tiếp nội dung cần hỏi.\n\n"
        "Kính chúc Quý công dân sức khỏe và nhiều điều tốt đẹp!"
    )


# Chức năng: Kiểm tra câu hỏi có ý định hỏi địa điểm, nơi nộp, nơi tiếp nhận hay không.
# Đầu vào: text - nội dung người dân gửi.
# Đầu ra: True nếu có ý định hỏi địa điểm; False nếu không phải.
# Vai trò: Giúp BOT xử lý câu hỏi nối tiếp như “làm ở đâu”, “nộp ở đâu”, “địa chỉ”.
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



# Vai trò: Ưu tiên tra cứu TRA_CUU_LIEN_HE trước khi tìm thủ tục để tránh nhầm “số điện thoại” sang VNeID.
# Chức năng: Nhận diện câu hỏi tra cứu liên hệ của người dân.
# Vai trò: Xác định intent TRA_CUU_LIEN_HE trước khi chuyển sang xử lý thủ tục hoặc AI.
def is_contact_question(text):
    t = normalize_text(text)

    contact_keys = [
        "lien he",
        "so dien thoai",
        "sdt",
        "dien thoai",
        "truc ban",
        "hotline",
        "gap can bo",
        "gap cskv",
        "gap chi huy",
        "chi huy",
        "lanh dao",
        "can bo truc",
        "cskv",
        "canh sat khu vuc",
        "dong chi",
        "ai la",
        "quan ly",
        "phu trach"
    ]

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
        "kien an"
    ]

    if any(k in t for k in contact_keys):
        return True

    if is_location_question(t) and any(k in t for k in agency_keys):
        return True

    return False
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
    return is_contact_question(t) and any(k in t for k in agency_keys)


def is_followup_detail_question(user_text):
    # Chức năng: Kiểm tra câu hỏi nối tiếp về chi tiết thủ tục.
    # Vai trò: Chỉ giữ context khi người dân hỏi tiếp về thủ tục hiện tại.
    text = normalize_text(user_text)
    detail_keywords = [
        "ho so", "ho so chi tiet", "giay to", "can giay to gi", "can gi",
        "dieu kien", "yeu cau", "yeu cau dieu kien",
        "trinh tu", "quy trinh", "quy trinh thuc hien",
        "cac buoc", "buoc thuc hien", "thu tuc thuc hien",
        "co quan tiep nhan", "noi tiep nhan", "noi thuc hien",
        "noi nop", "nop o dau", "lam o dau", "dia diem",
        "o dau", "o cho nao", "den dau", "den dau lam",
        "di dau lam", "toi dau lam",
        "vi tri", "ban do", "google map", "map",
        "thoi han", "bao lau", "may ngay",
        "le phi", "phi", "mat phi", "co mat phi khong",
        "co so phap ly", "can cu phap ly",
        "link", "link dvc", "dich vu cong",
        "ket qua", "luu y", "chi tiet",
    ]
    return any(kw in text for kw in detail_keywords)


# Chức năng: Tìm dòng liên hệ theo tên cơ quan hoặc họ tên cán bộ trong sheet TRA_CUU_LIEN_HE.
# Đầu vào: name - tên cơ quan/cán bộ cần tìm.
# Đầu ra: Một dòng dữ liệu liên hệ nếu tìm thấy; None nếu không có.
# Vai trò: Bổ sung thông tin liên hệ khi thủ tục có cột cơ quan tiếp nhận/thực hiện.
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


# Chức năng: Tạo tin nhắn chào mừng và danh mục hỗ trợ từ sheet MENU.
# Đầu vào: Không có.
# Đầu ra: Chuỗi menu chào mừng.
# Vai trò: Hiển thị danh mục chức năng chính của BOT khi người dân nhắn menu/lời chào.
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


# Chức năng: Tạo context sau khi người dân chọn một mục trong MENU.
# Đầu vào: row - dòng dữ liệu menu đã tìm thấy.
# Đầu ra: Dict context mới.
# Vai trò: Chuyển BOT sang nhóm thủ tục hoặc tra cứu liên hệ theo sheet được cấu hình trong MENU.
def menu_context(row):
    sheet = get_first(row, "SHEET_DU_LIEU", "SHEET")
    topic = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE")

    if sheet == "TRA_CUU_LIEN_HE":
        return {
            "sheet": sheet,
            "topic": topic,
            "stage": "contact_lookup",
            "procedure_id": "",
            "procedure_name": "",
            "page": 1,
            "last_suggestions": [],
        }

    return {
        "sheet": sheet,
        "topic": topic,
        "stage": "procedure_list",
        "procedure_id": "",
        "procedure_name": "",
        "page": 1,
        "last_suggestions": [],
    }


# Chức năng: Tạo danh sách thủ tục theo từng sheet THU_TUC_* có phân trang.
# Vai trò: Hiển thị danh sách thủ tục để người dân chọn số thứ tự.
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
    start_index = start + 1

    for i, row in enumerate(page_rows, start=start_index):
        name = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
        pid = get_first(row, "ID")
        suggestions.append({"index": i, "id": pid, "name": name})
        if name:
            lines.append(f"{i}. {name}")

    title = topic or sheet.replace("THU_TUC_", "")
    total = len(all_rows)
    has_next = end < total

    reply_parts = [
        "Tôi chưa xác định được chính xác Quý công dân đang hỏi về thủ tục nào.",
        f"Quý công dân vui lòng hỏi rõ hơn trong nhóm thủ tục: {title}.",
        "📌 Danh sách thủ tục hiện có:",
        "\n".join(lines),
        "➡️ Quý công dân vui lòng:\n• Nhắn số thứ tự của thủ tục cần tra cứu; hoặc\n• Nhập rõ tên thủ tục trong nhóm trên để BOT hỗ trợ chính xác.",
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


# Chức năng: Tạo câu trả lời khi người dân chọn một dòng trong MENU.
# Đầu vào: row - dòng MENU khớp với lựa chọn của người dân.
# Đầu ra: Tuple(reply, suggestions).
# Vai trò: Điều hướng từ MENU sang danh sách thủ tục hoặc nội dung mô tả theo sheet.
def answer_from_menu(row):
    title = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE")
    desc = get_first(row, "MO_TA", "MÔ_TẢ")
    sheet = get_first(row, "SHEET_DU_LIEU", "SHEET")

    if normalize_text(sheet) == "tra_cuu_lien_he":
        return str(desc or get_contact_lookup_message()).strip(), []

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


# Chức năng: Nhận diện nhóm thủ tục được nêu rõ trong câu hỏi.
# Vai trò: Giúp BOT mở đúng danh sách thủ tục theo nhóm dữ liệu Google Sheets.
# Chức năng: Nhận diện nhóm thủ tục khi người dân có ý định tra cứu thủ tục hành chính.
# Vai trò: Ngăn BOT mở sai menu khi câu hỏi chỉ có từ khóa nhưng không phải hỏi thủ tục.
def detect_explicit_topic(text):
    t = normalize_text(text)
    t_check = f" {t} "

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
            "dang ky xe", "cap bien so", "doi bien so", "cap lai bien so",
            "sang ten xe", "dang ky phuong tien", "dang ky xe may", "dang ky o to"
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

    procedure_intent_keys = [
        "thu tuc", "lam", "cap", "cap lai", "cap doi", "doi",
        "dang ky", "xin", "nop", "ho so", "giay to", "can gi",
        "o dau", "tai dau", "le phi", "thoi han", "ket qua",
        "truc tuyen", "online", "dich vu cong", "huong dan"
    ]

    menu_only_keys = []
    for keys in topic_map.values():
        menu_only_keys.extend(keys)

    has_procedure_intent = any(f" {k} " in t_check for k in procedure_intent_keys)
    is_exact_menu_key = any(t == normalize_text(k) for k in menu_only_keys)

    if not has_procedure_intent and not is_exact_menu_key:
        return None

    for sheet, keys in topic_map.items():
        if any(f" {normalize_text(k)} " in t_check for k in keys):
            return {
                "sheet": sheet,
                "topic": sheet.replace("THU_TUC_", ""),
                "stage": "procedure_list",
            }

    return None
# Chức năng: Tạo tiền tố ngữ cảnh dựa trên sheet thủ tục đang lưu trong context.
# Đầu vào: ctx - dict ngữ cảnh hiện tại của phiên chat.
# Đầu ra: Chuỗi tiền tố chủ đề hoặc chuỗi rỗng nếu không có sheet phù hợp.
# Vai trò: Giúp BOT hiểu các câu hỏi nối tiếp như hồ sơ, lệ phí, thời hạn, trình tự.
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


# Chức năng: Kiểm tra người dân chỉ nhập tên nhóm thủ tục, chưa nhập tên thủ tục cụ thể.
# Đầu vào: text - nội dung người dân gửi; explicit - kết quả nhận diện chủ đề.
# Đầu ra: True nếu là yêu cầu mở lại danh sách nhóm; False nếu có khả năng là tên thủ tục cụ thể.
# Vai trò: Giữ nguyên format danh sách 5 thủ tục khi người dân nhập lại tên nhóm như “căn cước”, “cư trú”, “đăng ký xe”.
def is_group_only_topic_request(text, explicit):
    t = normalize_text(text)
    sheet = explicit.get("sheet", "") if explicit else ""

    group_keys = {
        "THU_TUC_CCCD": [
            "can cuoc", "cccd", "the can cuoc"
        ],
        "THU_TUC_CUTRU": [
            "cu tru", "thu tuc cu tru", "dang ky cu tru"
        ],
        "THU_TUC_VNEID": [
            "vneid", "dinh danh", "dinh danh dien tu"
        ],
        "THU_TUC_PTGT": [
            "dang ky xe", "phuong tien", "phuong tien giao thong", "xe"
        ],
        "THU_TUC_PCCC": [
            "pccc", "phong chay", "chua chay", "phong chay chua chay"
        ],
        "THU_TUC_VKVLN": [
            "vkvln", "vu khi", "vat lieu no", "cong cu ho tro"
        ],
        "THU_TUC_LLTP": [
            "lltp", "ly lich tu phap", "phieu ly lich", "phieu ly lich tu phap"
        ],
        "THU_TUC_ANTT": [
            "antt", "nganh nghe antt", "nganh nghe dau tu kinh doanh co dieu kien ve antt",
            "kinh doanh co dieu kien"
        ],
    }

    return t in group_keys.get(sheet, [])


# Chức năng: Trả lời chi tiết một thủ tục theo câu hỏi nối tiếp của người dân.
# Đầu vào: row - dòng thủ tục; user_text - câu hỏi nối tiếp.
# Đầu ra: Chuỗi trả lời chi tiết theo trường dữ liệu phù hợp.
# Vai trò: Khai thác các cột HO_SO, TRINH_TU, THOI_HAN, LE_PHI... trong sheet THU_TUC_*.
def answer_procedure_detail(row, user_text):
    # Chức năng: Trả lời chi tiết một thủ tục theo câu hỏi nối tiếp của người dân.
    # Vai trò: Khai thác các cột HO_SO, NOI_NOP, TRINH_TU, THOI_HAN, LE_PHI... trong sheet THU_TUC_*.
    t = normalize_text(user_text)
    ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")

    if is_location_question(t):
        co_quan = get_first(
            row,
            "NOI_NOP",
            "NƠI_NỘP",
            "NOI_THUC_HIEN",
            "NƠI_THỰC_HIỆN",
            "CO_QUAN_TIEP_NHAN",
            "CƠ_QUAN_TIẾP_NHẬN",
            "CO_QUAN_THUC_HIEN",
            "CƠ_QUAN_THỰC_HIỆN",
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

# Chức năng: Tạo ngữ cảnh dữ liệu để chuyển sang AI fallback khi không tìm thấy câu trả lời trực tiếp.
# Đầu vào: ctx - context hiện tại.
# Đầu ra: Chuỗi thông tin thủ tục/danh sách thủ tục liên quan.
# Vai trò: Giúp AI có dữ liệu nền khi BOT phải dùng AI_FALLBACK.
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


# Chức năng: Chọn thủ tục từ danh sách gợi ý bằng số thứ tự.
# Đầu vào: text - số người dân nhập; ctx - context chứa last_suggestions.
# Đầu ra: Dòng thủ tục đã chọn hoặc None.
# Vai trò: Cho phép người dân chọn thủ tục sau khi BOT hiển thị danh sách.
def _select_from_suggestions(text, ctx):
    t = normalize_text(text)
    if not t.isdigit():
        return None

    idx = safe_int(t, default=-1)
    for item in ctx.get("last_suggestions", []) or []:
        if int(item.get("index", -99)) == idx:
            return find_procedure_by_id(item.get("id"))

    return None


# Chức năng: Tìm thủ tục phù hợp trong sheet thủ tục hiện tại.
# Đầu vào: text - câu hỏi/từ khóa; ctx - context hiện tại.
# Đầu ra: Dòng thủ tục phù hợp hoặc None.
# Vai trò: Khi đang ở một nhóm thủ tục, BOT chỉ tìm trong đúng sheet hiện tại.
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


# Chức năng: Tạo lại danh sách thủ tục dựa trên context hiện tại.
# Đầu vào: ctx - context có sheet/topic/page.
# Đầu ra: Tuple(reply, new_ctx) hoặc None.
# Vai trò: Dùng khi cần nhắc người dân chọn lại thủ tục trong nhóm hiện tại.
def _procedure_list_reply_for_context(ctx):
    sheet = ctx.get("sheet", "")
    topic = ctx.get("topic", "")
    page = ctx.get("page", 1)
    return _make_procedure_list_reply(sheet, topic=topic, page=page)


# Chức năng: Tạo thông báo yêu cầu chọn thủ tục cụ thể.
# Đầu vào: ctx - context hiện tại.
# Đầu ra: Tuple(reply, new_ctx).
# Vai trò: Tránh việc BOT đoán sai thủ tục khi người dân chưa chọn thủ tục rõ ràng.
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


# Chức năng: Tạo hướng dẫn tra cứu liên hệ theo từ khóa chuẩn.
# Đầu vào: Không có.
# Đầu ra: Chuỗi hướng dẫn tra cứu liên hệ.
# Vai trò: Hỗ trợ người dân sử dụng đúng nhóm TRA_CUU_LIEN_HE trong Google Sheets.
def get_contact_lookup_message():
    return (
        "📌 Tra cứu liên hệ\n\n"
        "Bạn đang truy cập hệ thống thông tin liên lạc của Công an phường Phù Liễn.\n\n"
        "Quý công dân vui lòng nhập đúng một trong các từ khóa chuẩn:\n"
        "1. liên hệ chỉ huy CAP\n"
        "2. liên hệ bộ phận CSKV\n"
        "3. liên hệ bộ phận AN NINH\n"
        "4. liên hệ bộ phận PCTP\n"
        "5. liên hệ bộ phận CSTT"
    )


# Chức năng: Kiểm tra người dân có nhập đúng từ khóa chuẩn tra cứu liên hệ hay không.
# Đầu vào: text - nội dung người dân gửi.
# Đầu ra: True nếu là từ khóa chuẩn; False nếu không phải.
# Vai trò: Cho phép tra cứu trực tiếp các nhóm liên hệ trong sheet TRA_CUU_LIEN_HE.
def is_contact_lookup_keyword(text):
    t = normalize_text(text)
    keys = [
        "lien he chi huy cap",
        "lien he bo phan cskv",
        "lien he bo phan an ninh",
        "lien he bo phan pctp",
        "lien he bo pctp",
        "lien he bo phan cstt",
    ]
    return t in keys

def is_contact_hint_question(text):
    # Chức năng: Nhận diện câu hỏi cần hỏi tiếp để xác định CSKV.
    # Vai trò: Chỉ kích hoạt khi người dân hỏi chung chung về CSKV, không áp dụng cho chỉ huy hoặc lãnh đạo.
    t = normalize_text(text)

    keys = [
        "gap cskv",
        "can gap cskv",
        "so dien thoai cskv",
        "lien he cskv",
        "tim cskv",
        "muon gap cskv",
        "can tim cskv",
    ]

    return any(k in t for k in keys)

# Chức năng: Tạo thông báo hướng dẫn vào mục tra cứu liên hệ.
# Đầu vào: Không có.
# Đầu ra: Chuỗi hướng dẫn.
# Vai trò: Giúp người dân dùng đúng MENU/TRA_CUU_LIEN_HE khi muốn tìm cán bộ hoặc bộ phận.
def get_contact_hint_message():
    return (
        "Để bảo đảm tra cứu đúng thông tin liên hệ, Quý công dân vui lòng truy cập mục “Tra cứu liên hệ”.\n\n"
        "Cách thực hiện:\n"
        "• Nhắn “menu”\n"
        "• Chọn mục Tra cứu liên hệ\n\n"
        "Sau đó nhập đúng từ khóa chuẩn theo danh sách hướng dẫn."
    )

def route_message(user_text, context=None):
    # Chức năng: Định tuyến chính toàn bộ tin nhắn người dân.
    # Vai trò: Bộ máy trung tâm xử lý MENU, TRA_CUU_LIEN_HE, THU_TUC_*, FAQ và AI fallback.
    ctx = dict(context or {})
    text = str(user_text or "").strip()
    text_norm = normalize_text(text)

    if not text:
        return DEFAULT_REPLY, "EMPTY", ctx, ""

    if is_reset_question(text):
        return get_end_message(), "RESET", {}, ""

    if is_greeting(text):
        return get_welcome_message(), "WELCOME", {}, ""

    if is_contact_lookup_keyword(text):
        if normalize_text(text) == "lien he bo phan cskv":
            return (
                "Quý công dân cần liên hệ đồng chí CSKV nào?\n\n"
                "Vui lòng nhập họ tên cán bộ nếu biết, hoặc nhập tên tổ dân phố công dân đang ở.\n\n"
                "Ví dụ: Tổ Ngọc Sơn, Tổ Đồng Tử; Tổ Quy Tức; Tổ Khúc Trì...\n\n"
                "Để thoát khỏi hệ thống tra cứu liên hệ, vui lòng nhập 'menu' hoặc gửi lời chào 'cảm ơn'.",
                "CSKV_ASK_NAME",
                {
                    "stage": "cskv_lookup",
                    "sheet": "TRA_CUU_LIEN_HE",
                    "topic": "Tra cứu CSKV",
                    "procedure_id": "",
                    "procedure_name": "",
                    "page": 1,
                    "last_suggestions": [],
                    "last_route": "CSKV_ASK_NAME",
                },
                "",
            )

        lien_he = search_lien_he(text, limit=20)
        if lien_he:
            return (
                format_multiple_results(lien_he, format_lien_he, limit=20),
                "TRA_CUU_LIEN_HE",
                {},
                "",
            )

    if is_contact_question(text):

        if is_contact_hint_question(text):
            return (
                "Quý công dân cần liên hệ đồng chí CSKV nào?\n\n"
                "Vui lòng nhập:\n"
                "• Họ tên cán bộ (nếu biết)\n"
                "hoặc\n"
                "• Tổ dân phố/khu vực cư trú.\n\n"
                "Ví dụ:\n"
                "• Đồng Tử\n"
                "• Quy Tức\n"
                "• Hoàng Quốc Việt\n\n"
                "Để thoát, vui lòng nhập 'menu' hoặc 'cảm ơn'.",
                "CONTACT_HINT",
                {
                    "stage": "cskv_lookup",
                    "sheet": "TRA_CUU_LIEN_HE",
                    "topic": "Tra cứu CSKV",
                    "procedure_id": "",
                    "procedure_name": "",
                    "page": 1,
                    "last_suggestions": [],
                    "last_route": "CSKV_ASK_NAME",
                },
                "",
            )

        lien_he = search_lien_he(text, limit=5)
        if lien_he:
            reply = format_multiple_results(lien_he, format_lien_he, limit=5)

            if len(lien_he) > 1:
                reply += (
                    "\n\nℹ️ Có nhiều kết quả phù hợp với thông tin vừa nhập. "
                    "Quý công dân vui lòng nhập rõ hơn họ tên đầy đủ, bộ phận hoặc địa bàn phụ trách để BOT tra cứu chính xác."
                )

            return reply, "TRA_CUU_LIEN_HE", {}, ""
    if ctx.get("stage") == "cskv_lookup":
        explicit = detect_explicit_topic(text)
        if explicit:
            grouped = _make_procedure_list_reply(
                explicit.get("sheet", ""),
                topic=explicit.get("topic", ""),
                page=1,
            )
            if grouped:
                reply, new_ctx = grouped
                return reply, "MENU_GROUP", new_ctx, ""

        lien_he = search_lien_he(text, limit=5)
        if lien_he:
            reply = format_multiple_results(lien_he, format_lien_he, limit=5)

            if len(lien_he) > 1:
                reply += (
                    "\n\nℹ️ Có nhiều cán bộ CSKV phù hợp với thông tin vừa nhập. "
                    "Quý công dân vui lòng nhập rõ hơn họ tên đầy đủ hoặc địa bàn phụ trách để BOT tra cứu chính xác."
                )

            new_ctx = {
                "stage": "cskv_lookup",
                "sheet": "TRA_CUU_LIEN_HE",
                "topic": "Tra cứu CSKV",
                "procedure_id": "",
                "procedure_name": "",
                "page": 1,
                "last_suggestions": [],
                "last_route": "TRA_CUU_LIEN_HE_CSKV",
            }

            return (
                reply + "\n\nQuý công dân có thể nhập tiếp tên cán bộ hoặc tổ dân phố khác để tra cứu CSKV.",
                "TRA_CUU_LIEN_HE_CSKV",
                new_ctx,
                "",
            )

        return (
            "Chưa tìm thấy cán bộ CSKV phù hợp với thông tin vừa nhập.\n\n"
            "Quý công dân vui lòng nhập rõ hơn theo một trong các cách:\n"
            "• Họ tên cán bộ CSKV nếu biết\n"
            "• Tên tổ dân phố/khu vực cần liên hệ\n\n"
            "Hoặc nhắn:\n"
            "• menu để quay lại danh mục chính\n"
            "• cảm ơn để kết thúc",
            "CSKV_NOT_FOUND",
            {
                "stage": "cskv_lookup",
                "sheet": "TRA_CUU_LIEN_HE",
                "topic": "Tra cứu CSKV",
                "procedure_id": "",
                "procedure_name": "",
                "page": 1,
                "last_suggestions": [],
                "last_route": "CSKV_NOT_FOUND",
            },
            "",
        )

    if is_specific_contact_question(text):
        lien_he = search_lien_he(text, limit=3)
        if lien_he:
            reply = format_multiple_results(lien_he, format_lien_he, limit=3)

            if len(lien_he) > 1:
                reply += (
                    "\n\nℹ️ Có nhiều kết quả phù hợp. "
                    "Quý công dân vui lòng nhập rõ hơn họ tên đầy đủ, bộ phận hoặc địa bàn phụ trách để BOT tra cứu chính xác."
                )

            return reply, "TRA_CUU_LIEN_HE_EXPLICIT", {}, ""

    selected = _select_from_suggestions(text, ctx)
    if selected:
        new_ctx = {
            "sheet": selected.get("_SHEET", ctx.get("sheet", "")),
            "topic": get_first(selected, "CHU_DE", "CHỦ_ĐỀ", default=ctx.get("topic", "")),
            "procedure_id": get_first(selected, "ID", "MA", "MÃ"),
            "procedure_name": get_first(selected, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
            "stage": "procedure",
            "page": ctx.get("page", 1),
            "last_suggestions": [],
            "last_route": "THU_TUC_SELECT",
        }
        return format_thu_tuc(selected), "THU_TUC_SELECT", new_ctx, ""

    if text_norm.isdigit() and ctx.get("sheet", "").startswith("THU_TUC_") and not ctx.get("procedure_id"):
        reply, new_ctx = _need_select_procedure_message(ctx)
        new_ctx["last_route"] = "NEED_PROCEDURE_SELECT"
        return reply, "NEED_PROCEDURE_SELECT", new_ctx, ""

    if text_norm.isdigit():
        menu = search_menu(text)
        if menu:
            reply, suggestions = answer_from_menu(menu)
            new_ctx = menu_context(menu)
            new_ctx["last_suggestions"] = suggestions
            new_ctx["page"] = 1
            new_ctx["last_route"] = "MENU"

            if new_ctx.get("sheet", "").startswith("THU_TUC_"):
                new_ctx["stage"] = "procedure_list"

            return reply, "MENU", new_ctx, ""

    if ctx.get("procedure_id") and is_followup_detail_question(text):
        explicit = detect_explicit_topic(text)

        if explicit and explicit.get("sheet") != ctx.get("sheet"):
            ctx = {}
        else:
            procedure = find_procedure_by_id(ctx.get("procedure_id"))
            if procedure:
                ctx["last_route"] = "PROCEDURE_CONTEXT"
                return answer_procedure_detail(procedure, text), "PROCEDURE_CONTEXT", ctx, ""

    explicit = detect_explicit_topic(text)
    if explicit:
        explicit_sheet = explicit.get("sheet", "")
        explicit_topic = explicit.get("topic", "")

        if is_group_only_topic_request(text, explicit):
            grouped = _make_procedure_list_reply(
                explicit_sheet,
                topic=explicit_topic,
                page=1,
            )
            if grouped:
                reply, new_ctx = grouped
                new_ctx["last_route"] = "MENU_GROUP"
                return reply, "MENU_GROUP", new_ctx, ""

        procedure_results = search_thu_tuc(text, limit=5, sheet=explicit_sheet)

        if procedure_results:
            best = procedure_results[0]
            best_score = safe_int(best.get("_SCORE", 0))
            second_score = safe_int(procedure_results[1].get("_SCORE", 0)) if len(procedure_results) > 1 else 0

            if best_score >= 35 and best_score >= second_score + 15:
                new_ctx = {
                    "sheet": best.get("_SHEET", explicit_sheet),
                    "topic": get_first(best, "CHU_DE", "CHỦ_ĐỀ", default=explicit_topic),
                    "procedure_id": get_first(best, "ID", "MA", "MÃ"),
                    "procedure_name": get_first(best, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                    "stage": "procedure",
                    "page": 1,
                    "last_suggestions": [],
                    "last_route": "THU_TUC_EXPLICIT",
                }
            if is_followup_detail_question(text):
                return answer_procedure_detail(best, text), "THU_TUC_EXPLICIT", new_ctx, ""
            
            return format_thu_tuc(best), "THU_TUC_EXPLICIT", new_ctx, ""
            
            suggestions = []
            lines = []

            for i, row in enumerate(procedure_results[:5], start=1):
                name = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
                pid = get_first(row, "ID", "MA", "MÃ")
                suggestions.append({"index": i, "id": pid, "name": name})
                if name:
                    lines.append(f"{i}. {name}")

            new_ctx = {
                "sheet": explicit_sheet,
                "topic": explicit_topic,
                "stage": "clarify_procedure",
                "procedure_id": "",
                "procedure_name": "",
                "page": 1,
                "last_suggestions": suggestions,
                "last_route": "CLARIFY_THU_TUC_IN_GROUP",
            }

            return (
                "Tôi tìm thấy một số thủ tục gần giống trong nhóm này. "
                "Quý công dân vui lòng chọn số tương ứng:\n\n"
                + "\n".join(lines),
                "CLARIFY_THU_TUC_IN_GROUP",
                new_ctx,
                "",
            )

        grouped = _make_procedure_list_reply(
            explicit_sheet,
            topic=explicit_topic,
            page=1,
        )
        if grouped:
            reply, new_ctx = grouped
            new_ctx["last_route"] = "MENU_GROUP"
            return reply, "MENU_GROUP", new_ctx, ""

    # Đang ở ngữ cảnh danh sách thủ tục:
    # - Nếu người dân hỏi tiếp về thủ tục => giữ ngữ cảnh.
    # - Nếu người dân chuyển sang câu hỏi mới/không liên quan => thoát ngữ cảnh và quay về định tuyến từ đầu.
    if ctx.get("sheet", "").startswith("THU_TUC_") and not ctx.get("procedure_id"):
        if is_next_page_question(text):
            next_ctx = dict(ctx)
            next_ctx["page"] = safe_int(ctx.get("page", 1), default=1) + 1
            grouped = _procedure_list_reply_for_context(next_ctx)
            if grouped:
                reply, new_ctx = grouped
                new_ctx["last_route"] = "PROCEDURE_LIST_NEXT"
                return reply, "PROCEDURE_LIST_NEXT", new_ctx, ""

        if not is_followup_detail_question(text):
            ctx = {}
        else:
            procedure = _find_procedure_in_current_sheet(text, ctx)
            if procedure:
                new_ctx = {
                    "sheet": procedure.get("_SHEET", ctx.get("sheet", "")),
                    "topic": get_first(procedure, "CHU_DE", "CHỦ_ĐỀ", default=ctx.get("topic", "")),
                    "procedure_id": get_first(procedure, "ID", "MA", "MÃ"),
                    "procedure_name": get_first(procedure, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                    "stage": "procedure",
                    "page": ctx.get("page", 1),
                    "last_suggestions": [],
                    "last_route": "THU_TUC_IN_CONTEXT",
                }
                return format_thu_tuc(procedure), "THU_TUC_IN_CONTEXT", new_ctx, ""

            reply, new_ctx = _need_select_procedure_message(ctx)
            new_ctx["last_route"] = "NEED_PROCEDURE_SELECT"
            return reply, "NEED_PROCEDURE_SELECT", new_ctx, ""
            
    # Không có ngữ cảnh + câu hỏi địa điểm quá mơ hồ.
    if (
        not ctx.get("procedure_id")
        and not explicit
        and is_location_question(text)
        and not is_specific_contact_question(text)
    ):
        lien_he = search_lien_he(text, limit=3)

        if lien_he and text_norm not in [
            "o dau", "lam o dau", "den dau", "den dau lam",
            "di dau lam", "toi dau lam", "vi tri", "map", "google map",
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
            "",
        )

    menu_keys = [
        "can cuoc", "cu tru", "vneid", "phuong tien giao thong",
        "dang ky xe", "ly lich tu phap", "pccc", "vkvln",
        "lien he", "tra cuu lien he",
    ]

    if text_norm in menu_keys:
        menu = search_menu(text)
        if menu:
            reply, suggestions = answer_from_menu(menu)
            new_ctx = menu_context(menu)
            new_ctx["last_suggestions"] = suggestions
            new_ctx["page"] = 1
            new_ctx["last_route"] = "MENU"

            if new_ctx.get("sheet", "").startswith("THU_TUC_"):
                new_ctx["stage"] = "procedure_list"

            return reply, "MENU", new_ctx, ""

    search_text = text

    if is_contact_question(text) or is_location_question(text) or text_norm in [
        "lien he",
        "so dien thoai",
        "truc ban",
        "google map",
        "ban do",
    ]:
        lien_he = search_lien_he(search_text, limit=3)
        if lien_he:
            return format_multiple_results(lien_he, format_lien_he, limit=3), "TRA_CUU_LIEN_HE", {}, ""

    thu_tuc_results = search_thu_tuc(search_text, limit=5, sheet=None)

    if thu_tuc_results:
        best = thu_tuc_results[0]
        best_score = safe_int(best.get("_SCORE", 0))
        second_score = safe_int(thu_tuc_results[1].get("_SCORE", 0)) if len(thu_tuc_results) > 1 else 0

        if best_score >= 20 and best_score >= second_score + 8:
            new_ctx = {
                "sheet": best.get("_SHEET", ""),
                "topic": get_first(best, "CHU_DE", "CHỦ_ĐỀ"),
                "procedure_id": get_first(best, "ID", "MA", "MÃ"),
                "procedure_name": get_first(best, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                "stage": "procedure",
                "page": 1,
                "last_suggestions": [],
                "last_route": "THU_TUC",
            }

            if is_followup_detail_question(text):
                return (
                    answer_procedure_detail(best, text),
                    "THU_TUC",
                    new_ctx,
                    "",
                )

            return format_thu_tuc(best), "THU_TUC", new_ctx, ""
        suggestions = []
        lines = []

        for i, row in enumerate(thu_tuc_results[:5], start=1):
            name = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
            pid = get_first(row, "ID", "MA", "MÃ")
            suggestions.append({"index": i, "id": pid, "name": name})
            if name:
                lines.append(f"{i}. {name}")

        ctx["last_suggestions"] = suggestions
        ctx["stage"] = "clarify_global"
        ctx["last_route"] = "CLARIFY_THU_TUC"

        return (
            "Tôi tìm thấy một số thủ tục gần giống nhau. "
            "Quý công dân vui lòng chọn số tương ứng:\n\n"
            + "\n".join(lines),
            "CLARIFY_THU_TUC",
            ctx,
            "",
        )

    if (
        ctx.get("procedure_id")
        or is_location_question(text)
        or is_contact_question(text)
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
            ctx["last_route"] = "FAQ"
            return format_multiple_results(faq, format_faq, limit=3), "FAQ", ctx, ""

    ctx["last_route"] = "DEFAULT"

    return (
        "Tôi chưa hiểu ý định Quý công dân đang hỏi về vấn đề gì.\n\n"
        "Quý công dân vui lòng nhắn tin câu từ có đầy đủ chủ đề cụ thể !.\n\n"
        "Ví dụ:\n"
        "• Hồ sơ cấp lại thẻ căn cước\n"
        "• Lệ phí đăng ký tạm trú\n"
        "• Thời hạn đăng ký xe\n"
        "• Đăng ký thường trú\n"
        "• Cấp đổi giấy phép sử dụng công cụ hỗ trợ\n\n"
        "Hoặc nhập 'menu' để xem danh mục hỗ trợ.",
        "DEFAULT",
        ctx,
        "",
    )


# Chức năng: Định tuyến tin nhắn người dân, chuẩn hóa kết quả trả về cho app.py.
# Vai trò: Là lớp trung gian để BOT quyết định trả lời từ Google Sheets hay chuyển sang AI.
def route_message_for_ai(user_text, context=None):
    result = {
        "reply": DEFAULT_REPLY,
        "source": "DEFAULT",
        "use_ai": True,
        "context": dict(context or {}),
        "ai_context": "",
    }

    try:
        reply, source, new_context, ai_context = route_message(
            user_text=user_text,
            context=context,
        )

        result["reply"] = reply
        result["source"] = source
        result["context"] = new_context
        result["ai_context"] = ai_context

        # Các nguồn đã có dữ liệu trong Google Sheets thì không gọi AI.
        sheet_sources = {
            "DEFAULT",
            "WELCOME",
            "RESET",
            "MENU",
            "MENU_GROUP",
            "THU_TUC",
            "THU_TUC_SELECT",
            "THU_TUC_EXPLICIT",
            "THU_TUC_IN_CONTEXT",
            "PROCEDURE_CONTEXT",
            "PROCEDURE_LIST_NEXT",
            "NEED_PROCEDURE_SELECT",
            "CLARIFY_THU_TUC",
            "CLARIFY_THU_TUC_IN_GROUP",
            "FAQ",
            "TRA_CUU_LIEN_HE",
            "TRA_CUU_LIEN_HE_CSKV",
            "TRA_CUU_LIEN_HE_EXPLICIT",
            "CONTACT_HINT",
            "CSKV_ASK_NAME",
            "CSKV_NOT_FOUND",
            "ASK_TOPIC",
        }

        result["use_ai"] = source not in sheet_sources

    except Exception as e:
        print(f"[ROUTER ERROR] {e}")

        result["reply"] = DEFAULT_REPLY
        result["source"] = "ROUTER_ERROR"
        result["use_ai"] = True
        result["context"] = dict(context or {})
        result["ai_context"] = ""

    return result
