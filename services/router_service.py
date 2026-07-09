
from services.text_utils import normalize_text, get_first, safe_int, compact
from services.sheet_api import read_menu, read_lien_he, read_setting_chat, read_setting_ai, read_thongtin, read_thu_tuc_sheet_names, read_thu_tuc_sheet
from services.logger import debug_print
from services.search_engine import (
    search_menu,
    search_lien_he,
    detect_bo_phan_contact,
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
TECHNICAL_FALLBACK_REPLY = "Xin lỗi, hiện hệ thống chưa xử lý được yêu cầu này. Quý công dân vui lòng nhập menu hoặc hỏi rõ hơn."


# Chức năng: Lấy cấu hình hội thoại từ sheet SETTING_CHAT.
# Vai trò: Không để nội dung trả lời nghiệp vụ nằm cứng trong Python.
def _chat_setting(key, default=""):
    data = read_setting_chat() or {}
    return str(data.get(key) or default or "").strip()


# Chức năng: Lấy câu trả lời mặc định từ SETTING_CHAT.
# Vai trò: Không phụ thuộc DEFAULT_REPLY hardcode trong config.py.
def get_default_reply():
    return _chat_setting("UNKNOWN_MESSAGE", TECHNICAL_FALLBACK_REPLY)


# Chức năng: Lấy cấu hình AI từ sheet SETTING_AI.
# Vai trò: Điều khiển AI Optional mà không hardcode trạng thái trong Python.
def _ai_setting(key, default=""):
    data = read_setting_ai() or {}
    return str(data.get(key) or default or "").strip()


# Chức năng: Chuyển giá trị cấu hình sheet thành boolean.
# Vai trò: Giúp router đọc đúng các cờ bật/tắt AI Optional.
def _as_bool(value, default=False):
    text = normalize_text(value)
    if not text:
        return default
    return text in ["true", "1", "yes", "on", "bat", "bật", "enable", "enabled"]


# Chức năng: Kiểm tra AI có được phép hoạt động như lớp phụ trợ hay không.
# Vai trò: Bảo đảm Gemini không trở thành luồng chính của BOT.
def _ai_optional_enabled():
    if normalize_text(_ai_setting("AI_IS_CORE", "FALSE")) in ["true", "1", "yes", "on"]:
        return False
    if normalize_text(_ai_setting("AI_MODE", "OPTIONAL")) not in ["optional", "tuy chon", "tùy chọn"]:
        return False
    return _as_bool(_ai_setting("AI_ENABLED", "TRUE"), True)


# Chức năng: Kiểm tra câu hỏi có dấu hiệu là thủ tục/nghiệp vụ nhưng chưa có dữ liệu sheet.
# Vai trò: Chặn AI tự suy diễn thủ tục khi Google Sheets không có căn cứ.
def _looks_like_procedure_without_data(user_text):
    t = normalize_text(user_text)
    keys = [
        "thu tuc", "ho so", "giay to", "dieu kien", "le phi", "thoi han",
        "noi nop", "co quan thuc hien", "cap", "dang ky", "xac nhan",
        "cap lai", "cap doi", "lam", "nop", "dich vu cong",
    ]
    return any(k in t for k in keys)


# Chức năng: Quyết định có chuyển câu hỏi sang Gemini hay không.
# Vai trò: Chỉ cho phép AI khi phù hợp cấu hình và không làm thay nghiệp vụ Google Sheets.
def _should_use_ai(user_text, source, ai_context=""):
    if not _ai_optional_enabled():
        return False

    if ai_context and _as_bool(_ai_setting("ENABLE_AI_SUMMARIZE", "TRUE"), True):
        return True

    if source in ["DEFAULT", "ROUTER_ERROR", "EMPTY"]:
        if _looks_like_procedure_without_data(user_text):
            return _as_bool(_ai_setting("ALLOW_AI_PROCEDURE_WITHOUT_DATA", "FALSE"), False)
        return _as_bool(_ai_setting("ENABLE_AI_GENERAL_KNOWLEDGE", "FALSE"), False)

    return False


# Chức năng: Tách danh sách từ khóa từ một ô dữ liệu Google Sheets.
# Vai trò: Dùng dữ liệu sheet thay cho hardcode từ khóa nghiệp vụ trong router.
def _split_keywords(value):
    raw = str(value or "").replace(";", ",").replace("|", ",")
    return [x.strip() for x in raw.split(",") if x and x.strip()]


# Chức năng: Kiểm tra một dòng dữ liệu có trạng thái hoạt động hay không.
# Vai trò: Bảo đảm router chỉ xử lý các dòng đang bật trong Google Sheets.
def _is_on(row):
    status = normalize_text(get_first(row, "TRANG_THAI", "STATUS", default="ACTIVE"))
    return status not in ["off", "inactive", "false", "0", "no", "khong", "ngung", "dung"]


# Chức năng: Lấy các dòng MENU đang hoạt động từ Google Sheets.
# Vai trò: MENU là nguồn định tuyến nghiệp vụ duy nhất của router.
def _menu_rows():
    return [r for r in read_menu() if _is_on(r)]


# Chức năng: Tính điểm khớp giữa câu hỏi và một dòng MENU.
# Vai trò: Chọn nhóm nghiệp vụ bằng TEN_CHUC_NANG/TU_KHOA trong Google Sheets.
def _score_menu_row(text, row):
    t = normalize_text(text)
    t_box = f" {t} "
    score = 0

    title = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE")
    desc = get_first(row, "MO_TA", "MÔ_TẢ")
    sheet = get_first(row, "SHEET_DU_LIEU", "SHEET")
    keywords = _split_keywords(get_first(row, "TU_KHOA", "TỪ_KHÓA", "KEYWORDS"))

    for value, weight in [(title, 30), (desc, 8), (sheet, 5)]:
        n = normalize_text(value)
        if n and (t == n or f" {n} " in t_box or n in t):
            score += weight

    for kw in keywords:
        n = normalize_text(kw)
        if not n:
            continue
        if t == n:
            score += 35
        elif f" {n} " in t_box or n in t:
            score += 15

    return score


# Chức năng: Tìm dòng MENU phù hợp nhất bằng dữ liệu trong sheet MENU.
# Vai trò: Thay thế toàn bộ mapping nhóm thủ tục hardcode trong router cũ.
def _match_menu_by_data(text):
    best = None
    best_score = 0
    second_score = 0

    for row in _menu_rows():
        score = _score_menu_row(text, row)
        if score > best_score:
            second_score = best_score
            best_score = score
            best = row
        elif score > second_score:
            second_score = score

    if best and best_score >= 25 and best_score >= second_score + 5:
        return best
    return None


# Chức năng: Chọn dòng MENU theo số thứ tự hoặc ID trong Google Sheets.
# Vai trò: Bảo đảm người dân nhập số menu vẫn định tuyến đúng theo dữ liệu MENU.
def _match_menu_by_number(text):
    t = normalize_text(text)
    if not t.isdigit():
        return None

    number = safe_int(t, default=-1)
    rows = _menu_rows()

    for index, row in enumerate(rows, start=1):
        row_id = safe_int(get_first(row, "ID", "MA", "MÃ"), default=index)
        if number == index or number == row_id:
            return row

    return None


# Chức năng: Kiểm tra lệnh mở menu hoặc bắt đầu phiên chat.
# Vai trò: Nhóm lệnh kỹ thuật được phép giữ trong Python.
def is_greeting(text):
    return normalize_text(text) in [
        "xin chao", "chao", "chao ban", "hello", "hi", "alo",
        "menu", "danh muc", "bat dau", "0",
        "ket noi bot cap", "#ket noi bot cap", "ket_noi_bot_cap", "#ket_noi_bot_cap",
    ]


# Chức năng: Kiểm tra lệnh kết thúc, reset hoặc quay lại.
# Vai trò: Nhóm lệnh điều khiển phiên được phép giữ trong Python.
def is_reset_question(text):
    return normalize_text(text) in [
        "huy", "thoat", "lam lai", "menu chinh", "quay lai", "back",
        "xoa", "reset", "xong", "xong roi", "da ro", "toi hieu roi",
        "duoc roi", "ok roi", "cam on", "cam on ban", "ok cam on",
        "cam on nhe", "cam on nhieu", "thank", "thanks", "thank you",
    ]


# Chức năng: Kiểm tra yêu cầu xem tiếp danh sách.
# Vai trò: Hỗ trợ phân trang kỹ thuật cho danh sách thủ tục.
def is_next_page_question(text):
    return normalize_text(text) in ["xem tiep", "xem them", "tiep", "trang tiep", "next"]


# Chức năng: Tạo thông điệp kết thúc phiên từ SETTING_CHAT.
# Vai trò: Loại bỏ lời chào/kết thúc hardcode theo đơn vị.
def get_end_message():
    default = "🙏 Cảm ơn Quý công dân đã sử dụng hệ thống. Khi cần hỗ trợ thêm, vui lòng nhắn 'menu'."
    return _chat_setting("GOODBYE_MESSAGE", default)


# Chức năng: Kiểm tra câu hỏi nối tiếp về nơi thực hiện hoặc địa chỉ.
# Vai trò: Nhận diện ý định kỹ thuật để đọc cột địa điểm từ dữ liệu thủ tục/liên hệ.
def is_location_question(text):
    t = normalize_text(text)
    keys = [
        "o dau", "dia chi", "dia diem", "noi lam", "lam o dau", "nop o dau",
        "co quan tiep nhan", "tiep nhan", "noi tiep nhan", "co quan thuc hien",
        "noi thuc hien", "noi nop", "den dau", "den dau lam", "di dau lam",
        "toi dau lam", "lam cho nao", "nop cho nao", "vi tri", "ban do", "google map", "map",
    ]
    return any(k in t for k in keys)


# Chức năng: Kiểm tra câu hỏi có ý định tra cứu liên hệ hay không.
# Vai trò: Chỉ chuyển sang TRA_CUU_LIEN_HE khi người dân hỏi rõ về liên hệ, số điện thoại, cán bộ hoặc bộ phận.
def is_contact_question(text):
    t = normalize_text(text)

    if detect_bo_phan_contact(text):
        return True

    contact_intent_keys = [
        "lien he", "so dien thoai", "sdt", "dien thoai",
        "hotline", "gap can bo", "gap dong chi", "gap dc",
        "can bo phu trach", "ai phu trach", "truc ban",
        "cskv", "canh sat khu vuc", "to dan pho", "tdp",
        "to an ninh", "to cstt", "to pctp", "to tong hop",
        "chi huy", "lanh dao", "truong cap", "truong cong an phuong",
        "pho cap", "pho cong an phuong", "pho truong cap", "pho truong cong an phuong",
    ]

    return any(k in t for k in contact_intent_keys)


# Chức năng: Kiểm tra câu hỏi có ý định liên hệ rõ ràng.
# Vai trò: Cho phép ưu tiên TRA_CUU_LIEN_HE nhưng không cướp luồng phản ánh ANTT/FAQ.
def _is_clear_contact_intent(text):
    t = normalize_text(text)
    clear_keys = [
        "lien he", "so dien thoai", "sdt", "dien thoai",
        "hotline", "gap", "dong chi", "dc", "can bo",
        "ai phu trach", "chi huy", "lanh dao",
        "truong cap", "truong cong an phuong",
        "pho cap", "pho truong cap", "pho cong an phuong", "pho truong cong an phuong",
    ]
    return any(k in t for k in clear_keys)


# Chức năng: Kiểm tra câu hỏi nối tiếp về chi tiết thủ tục.
# Vai trò: Giữ đúng context thủ tục hiện tại khi người dân hỏi hồ sơ, lệ phí, thời hạn.
def is_followup_detail_question(user_text):
    text = normalize_text(user_text)
    detail_keywords = [
        "ho so", "giay to", "can gi", "dieu kien", "yeu cau", "trinh tu",
        "quy trinh", "cac buoc", "buoc thuc hien", "co quan tiep nhan",
        "noi tiep nhan", "noi thuc hien", "noi nop", "nop o dau", "lam o dau",
        "dia diem", "o dau", "thoi han", "bao lau", "may ngay", "le phi",
        "phi", "mat phi", "co so phap ly", "can cu phap ly", "link",
        "dich vu cong", "ket qua", "luu y", "chi tiet", "buu dien",
        "buu chinh", "chuyen phat", "gui ve nha", "nhan tai nha",
        "nhan ket qua","lam truc tuyen", "truc tuyen",
        "online", "lam online", "làm online", "nop online", "nộp online",
        "lam truc tuyen", "nop truc tuyen", "co lam online duoc khong",
    ]
    return any(kw in text for kw in detail_keywords) or is_location_question(text)

# Chức năng: Tìm liên hệ theo tên cơ quan/cán bộ từ TRA_CUU_LIEN_HE.
# Vai trò: Bổ sung nơi tiếp nhận cho thủ tục bằng dữ liệu Google Sheets.
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
        if ten_norm and (name_norm in ten_norm or ten_norm in name_norm):
            return row

    return None


# Chức năng: Tạo tin nhắn chào mừng và danh mục hỗ trợ từ MENU/SETTING_CHAT.
# Vai trò: Không hardcode danh mục nghiệp vụ trong Python.
def get_welcome_message():
    prefix = _chat_setting("WELCOME_MESSAGE", "🇻🇳 CHÀO MỪNG QUÝ CÔNG DÂN")
    rows = _menu_rows()
    lines = []

    for i, row in enumerate(rows, start=1):
        title = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE", "MO_TA", "MÔ_TẢ")
        if title:
            lines.append(f"{i}. {title}")

    if not lines:
        return prefix

    return (
        f"{prefix}\n\n"
        "📋 DANH MỤC HỖ TRỢ\n"
        + "\n".join(lines)
        + "\n\n💬 Quý công dân có thể nhập số thứ tự hoặc nhập trực tiếp nội dung cần hỏi."
    )


# Chức năng: Tạo context sau khi người dân chọn một mục trong MENU.
# Vai trò: Chuyển BOT sang sheet được cấu hình tại MENU.SHEET_DU_LIEU.
def menu_context(row):
    sheet = get_first(row, "SHEET_DU_LIEU", "SHEET")
    topic = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE")
    stage = "contact_lookup" if normalize_text(sheet) == "tra_cuu_lien_he" else "procedure_list"

    return {
        "sheet": sheet,
        "topic": topic,
        "stage": stage,
        "procedure_id": "",
        "procedure_name": "",
        "page": 1,
        "last_suggestions": [],
    }


# Chức năng: Tạo danh sách thủ tục theo sheet THU_TUC_* có phân trang.
# Vai trò: Hiển thị lựa chọn thủ tục từ dữ liệu Google Sheets.
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
        page = max(((len(all_rows) - 1) // PAGE_SIZE) + 1, 1)
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        page_rows = all_rows[start:end]

    suggestions = []
    lines = []
    for i, row in enumerate(page_rows, start=start + 1):
        name = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
        pid = get_first(row, "ID", "MA", "MÃ")
        suggestions.append({"index": i, "id": pid, "name": name})
        if name:
            lines.append(f"{i}. {name}")

    title = topic or sheet.replace("THU_TUC_", "")
    has_next = end < len(all_rows)
    reply_parts = [
        f"📌 {title}",
        "Quý công dân vui lòng chọn thủ tục:",
        "\n".join(lines),
        "Nhắn số thứ tự để chọn thủ tục hoặc nhập từ khóa gần đúng của thủ tục cần hỏi.",
    ]
    reply_parts.append("Nhắn \"xem tiếp\" để xem thêm thủ tục." if has_next else "Đã hiển thị hết danh sách thủ tục trong nhóm này.")

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


# Chức năng: Tạo câu trả lời khi người dân chọn một dòng MENU.
# Vai trò: MENU quyết định sheet, mô tả và hướng xử lý tiếp theo.
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
                reply = reply.replace(f"📌 {title}\n\n", f"📌 {title}\n\n{desc}\n\n", 1)
            return reply, new_ctx.get("last_suggestions", [])

    parts = []
    if title:
        parts.append(f"📌 {title}")
    if desc:
        parts.append(str(desc))
    if sheet:
        parts.append(f"Quý công dân vui lòng nhập nội dung cụ thể để BOT tra cứu trong nhóm dữ liệu: {sheet}")
    return ("\n\n".join(parts) if parts else get_welcome_message()), []


# Chức năng: Nhận diện nhóm thủ tục bằng MENU thay vì mapping hardcode.
# Vai trò: Giúp BOT mở đúng sheet THU_TUC_* theo Google Sheets.
def detect_explicit_topic(text):
    row = _match_menu_by_data(text)
    if not row:
        return None

    sheet = get_first(row, "SHEET_DU_LIEU", "SHEET")
    if not sheet or not sheet.startswith("THU_TUC_"):
        return None

    return {
        "sheet": sheet,
        "topic": get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE") or sheet.replace("THU_TUC_", ""),
        "stage": "procedure_list",
    }


# Chức năng: Lấy tiền tố ngữ cảnh từ tên nhóm MENU hiện tại.
# Vai trò: Không dùng mapping sheet-nghiệp vụ hardcode.
def context_prefix(ctx):
    return (str(ctx.get("topic") or "") + " ") if ctx.get("topic") else ""


# Chức năng: Kiểm tra người dân chỉ nhập tên nhóm thủ tục.
# Vai trò: Dùng TEN_CHUC_NANG/TU_KHOA trong MENU để mở danh sách nhóm.
def is_group_only_topic_request(text, explicit):
    if not explicit:
        return False

    t = normalize_text(text)
    sheet = explicit.get("sheet", "")
    for row in _menu_rows():
        if get_first(row, "SHEET_DU_LIEU", "SHEET") != sheet:
            continue
        values = [get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE")]
        values.extend(_split_keywords(get_first(row, "TU_KHOA", "TỪ_KHÓA", "KEYWORDS")))
        if any(t == normalize_text(v) for v in values if v):
            return True
    return False

# Chức năng: Kiểm tra sheet thủ tục có phải nhóm VNeID hay không.
# Vai trò: Tách luồng VNeID khỏi nguyên tắc định tuyến thủ tục bằng TU_KHOA.
def _is_vneid_sheet(sheet_name):
    return normalize_text(sheet_name) == "thu_tuc_vneid"


# Chức năng: Lấy mã thủ tục chuẩn từ một dòng thủ tục.
# Vai trò: Dùng RELATED_ID của FAQ để bổ sung đúng thủ tục đã xác định.
def _procedure_id(row):
    return get_first(row, "ID", "MA", "MÃ")


# Chức năng: Tính điểm khớp thủ tục chỉ bằng cột TU_KHOA.
# Vai trò: Bảo đảm THU_TUC_* thường được định tuyến bằng TU_KHOA, không bị FAQ cướp luồng.
def _score_procedure_by_tu_khoa(text, row):
    t = normalize_text(text)
    t_box = f" {t} "
    score = 0

    pid = normalize_text(_procedure_id(row))
    if pid and pid in t:
        score += 80

    keywords = _split_keywords(get_first(row, "TU_KHOA", "TỪ_KHÓA", "KEYWORDS"))
    for kw in keywords:
        n = normalize_text(kw)
        if not n:
            continue
        if t == n:
            score += 70
        elif f" {n} " in t_box or n in t:
            score += 45
        else:
            parts = [p for p in n.split() if len(p) >= 3]
            if parts and all(p in t for p in parts):
                score += 25

    return score


# Chức năng: Tìm thủ tục theo TU_KHOA trong các sheet THU_TUC_*.
# Vai trò: Dùng Google Sheets làm nguồn định tuyến chính cho thủ tục thường.
def _search_thu_tuc_by_tu_khoa(text, sheet=None, limit=5, include_vneid=False):
    rows = []

    if sheet:
        if _is_vneid_sheet(sheet) and not include_vneid:
            return []
        rows = read_thu_tuc_sheet(sheet)
    else:
        for sheet_name in read_thu_tuc_sheet_names():
            if _is_vneid_sheet(sheet_name) and not include_vneid:
                continue
            rows.extend(read_thu_tuc_sheet(sheet_name))

    scored = []
    for row in rows:
        score = _score_procedure_by_tu_khoa(text, row)
        if score > 0:
            item = dict(row)
            item["_SCORE"] = score
            scored.append(item)

    scored.sort(key=lambda x: safe_int(x.get("_SCORE", 0)), reverse=True)
    return scored[:limit]


# Chức năng: Tìm FAQ bổ sung theo NGU_CANH và RELATED_ID của thủ tục đã xác định.
# Vai trò: FAQ chỉ bổ sung ý định chi tiết, không thay thế dữ liệu chính trong THU_TUC_*.
def _faq_supplement_for_procedure(row, user_text, ngu_canh):
    pid = normalize_text(_procedure_id(row))
    if not pid:
        return ""

    target_context = normalize_text(ngu_canh)
    faq_rows = search_faq(user_text, limit=5) or []

    for faq_row in faq_rows:
        faq_context = normalize_text(get_first(faq_row, "NGU_CANH", "NGỮ_CẢNH"))
        if faq_context != target_context:
            continue

        related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED", "MA_THU_TUC", "MÃ_THỦ_TỤC"))
        if not any(normalize_text(x) == pid for x in related_ids):
            continue

        extra = format_faq(faq_row)
        if extra:
            return "\n\nℹ️ Thông tin bổ sung:\n" + compact(extra, 700)

    return ""


# Chức năng: Lọc FAQ thường không có RELATED_ID và không phải THONGTIN.
# Vai trò: Không để FAQ có RELATED_ID trả danh sách khi chưa đúng luồng.
def _normal_faq_rows(faq_rows):
    results = []
    for row in faq_rows or []:
        ngu_canh = normalize_text(get_first(row, "NGU_CANH", "NGỮ_CẢNH"))
        related_id = get_first(row, "RELATED_ID", "RELATED", "MA_THU_TUC", "MÃ_THỦ_TỤC")
        if ngu_canh == "thongtin":
            continue
        if related_id:
            continue
        results.append(row)
    return results

# Chức năng: Lấy NGU_CANH phù hợp từ FAQ theo thủ tục hiện tại.
# Vai trò: Dùng FAQ làm lớp hiểu ý định, không dùng FAQ để thay thế dữ liệu THU_TUC_*.
def _faq_context_for_procedure(row, user_text):
    pid = normalize_text(_procedure_id(row))
    faq_rows = search_faq(user_text, limit=5) or []

    for faq_row in faq_rows:
        ngu_canh = normalize_text(get_first(faq_row, "NGU_CANH", "NGỮ_CẢNH"))
        if not ngu_canh or ngu_canh == "thongtin":
            continue

        related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED", "MA_THU_TUC", "MÃ_THỦ_TỤC"))
        if related_ids and any(normalize_text(x) == pid for x in related_ids):
            return ngu_canh.upper()

    for faq_row in faq_rows:
        ngu_canh = normalize_text(get_first(faq_row, "NGU_CANH", "NGỮ_CẢNH"))
        related_id = get_first(faq_row, "RELATED_ID", "RELATED", "MA_THU_TUC", "MÃ_THỦ_TỤC")

        if ngu_canh and ngu_canh != "thongtin" and not related_id:
            return ngu_canh.upper()

    return ""


# Chức năng: Lấy dữ liệu thủ tục theo NGU_CANH.
# Vai trò: Chuyển ý định FAQ thành cột dữ liệu tương ứng trong THU_TUC_*.
def _procedure_value_by_context(row, ngu_canh):
    c = normalize_text(ngu_canh)

    if c == "ho_so":
        return "📄", "Hồ sơ", get_first(row, "HO_SO", "HỒ_SƠ", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")

    if c == "dieu_kien":
        return "✅", "Điều kiện", get_first(row, "DIEU_KIEN", "ĐIỀU_KIỆN")

    if c == "trinh_tu":
        return "📝", "Trình tự thực hiện", get_first(row, "TRINH_TU", "TRÌNH_TỰ", "QUY_TRINH", "QUY_TRÌNH")

    if c == "noi_nop" or c == "noi_thuc_hien":
        return "📍", "Cơ quan/nơi tiếp nhận", get_first(row, "NOI_THUC_HIEN", "NƠI_THỰC_HIỆN", "NOI_NOP", "NƠI_NỘP", "CO_QUAN_TIEP_NHAN", "CƠ_QUAN_TIẾP_NHẬN", "CO_QUAN_THUC_HIEN", "CƠ_QUAN_THỰC_HIỆN", "DON_VI_GIAI_QUYET", "ĐƠN_VỊ_GIẢI_QUYẾT")

    if c == "thoi_han":
        return "⏱", "Thời hạn", get_first(row, "THOI_HAN", "THỜI_HẠN")

    if c == "le_phi":
        return "💰", "Lệ phí", get_first(row, "LE_PHI", "LỆ_PHÍ", "PHI")

    if c == "ket_qua":
        return "✅", "Kết quả", get_first(row, "KET_QUA", "KẾT_QUẢ")

    if c == "co_so_phap_ly":
        return "⚖️", "Cơ sở pháp lý", get_first(row, "CO_SO_PHAP_LY", "CƠ_SỞ_PHÁP_LÝ")

    if c == "link_dvc":
        return "🔗", "Làm trực tuyến", get_first(row, "LINK_DVC", "LINK")

    return "", "", ""

# Chức năng: Trả lời chi tiết một thủ tục theo câu hỏi nối tiếp.
# Vai trò: Ưu tiên cột dữ liệu của THU_TUC_*, chỉ bổ sung FAQ khi NGU_CANH và RELATED_ID khớp.
def answer_procedure_detail(row, user_text):
    t = normalize_text(user_text)
    ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
    faq_context = _faq_context_for_procedure(row, user_text)

    if faq_context == "DIEU_KIEN":
        value = get_first(row, "DIEU_KIEN", "ĐIỀU_KIỆN")
        reply = f"✅ Điều kiện - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "DIEU_KIEN")

    if faq_context in ["NOI_NOP", "NOI_THUC_HIEN"]:
        co_quan = get_first(row, "NOI_THUC_HIEN", "NƠI_THỰC_HIỆN", "NOI_NOP", "NƠI_NỘP", "CO_QUAN_TIEP_NHAN", "CƠ_QUAN_TIẾP_NHẬN", "CO_QUAN_THUC_HIEN", "CƠ_QUAN_THỰC_HIỆN", "DON_VI_GIAI_QUYET", "ĐƠN_VỊ_GIẢI_QUYẾT")
        lien_he = find_lien_he_by_ten_co_quan(co_quan)
        if lien_he:
            return format_lien_he(lien_he)
        reply = f"📍 Cơ quan/nơi tiếp nhận - {ten}\n\n{compact(co_quan, 1800)}" if co_quan else _chat_setting("ASK_LOCATION_DETAIL", f"📍 Cơ quan/nơi tiếp nhận - {ten}\n\nChưa có dữ liệu nơi tiếp nhận trong Google Sheets.")
        return reply + _faq_supplement_for_procedure(row, user_text, "NOI_NOP")

    if faq_context == "HO_SO":
        value = get_first(row, "HO_SO", "HỒ_SƠ", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")
        reply = f"📄 Hồ sơ - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "HO_SO")

    if faq_context == "TRINH_TU":
        value = get_first(row, "TRINH_TU", "TRÌNH_TỰ", "QUY_TRINH", "QUY_TRÌNH")
        reply = f"📝 Trình tự thực hiện - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "TRINH_TU")

    if faq_context == "THOI_HAN":
        value = get_first(row, "THOI_HAN", "THỜI_HẠN")
        reply = f"⏱ Thời hạn - {ten}\n\n{value}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "THOI_HAN")

    if faq_context == "LE_PHI":
        value = get_first(row, "LE_PHI", "LỆ_PHÍ", "PHI")
        reply = f"💰 Lệ phí - {ten}\n\n{value}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "LE_PHI")

    if faq_context == "KET_QUA":
        value = get_first(row, "KET_QUA", "KẾT_QUẢ")
        reply = f"✅ Kết quả - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "KET_QUA")

    if faq_context == "CO_SO_PHAP_LY":
        value = get_first(row, "CO_SO_PHAP_LY", "CƠ_SỞ_PHÁP_LÝ")
        reply = f"⚖️ Cơ sở pháp lý - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "CO_SO_PHAP_LY")

    if faq_context == "LINK_DVC":
        value = get_first(row, "LINK_DVC", "LINK")
        reply = f"🔗 Làm trực tuyến - {ten}\n\nQuý công dân có thể thực hiện trực tuyến qua Cổng Dịch vụ công nếu thủ tục được hỗ trợ.\n\n{value}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "LINK_DVC")

    if "dieu kien" in t or "yeu cau" in t:
        value = get_first(row, "DIEU_KIEN", "ĐIỀU_KIỆN")
        reply = f"✅ Điều kiện - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "DIEU_KIEN")

    if is_location_question(t):
        co_quan = get_first(row, "NOI_THUC_HIEN", "NƠI_THỰC_HIỆN", "NOI_NOP", "NƠI_NỘP", "CO_QUAN_TIEP_NHAN", "CƠ_QUAN_TIẾP_NHẬN", "CO_QUAN_THUC_HIEN", "CƠ_QUAN_THỰC_HIỆN", "DON_VI_GIAI_QUYET", "ĐƠN_VỊ_GIẢI_QUYẾT")
        lien_he = find_lien_he_by_ten_co_quan(co_quan)
        if lien_he:
            return format_lien_he(lien_he)
        reply = f"📍 Cơ quan/nơi tiếp nhận - {ten}\n\n{compact(co_quan, 1800)}" if co_quan else _chat_setting("ASK_LOCATION_DETAIL", f"📍 Cơ quan/nơi tiếp nhận - {ten}\n\nChưa có dữ liệu nơi tiếp nhận trong Google Sheets.")
        return reply + _faq_supplement_for_procedure(row, user_text, "NOI_NOP")

    if "ho so" in t or "giay to" in t or "can gi" in t or "chi tiet" in t:
        value = get_first(row, "HO_SO", "HỒ_SƠ", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")
        reply = f"📄 Hồ sơ - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "HO_SO")

    if "trinh tu" in t or "quy trinh" in t or "cac buoc" in t or "buoc thuc hien" in t:
        value = get_first(row, "TRINH_TU", "TRÌNH_TỰ", "QUY_TRINH", "QUY_TRÌNH")
        reply = f"📝 Trình tự thực hiện - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "TRINH_TU")

    if "bao lau" in t or "thoi han" in t or "may ngay" in t:
        value = get_first(row, "THOI_HAN", "THỜI_HẠN")
        reply = f"⏱ Thời hạn - {ten}\n\n{value}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "THOI_HAN")

    if "le phi" in t or "mat phi" in t or t == "phi":
        value = get_first(row, "LE_PHI", "LỆ_PHÍ", "PHI")
        reply = f"💰 Lệ phí - {ten}\n\n{value}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "LE_PHI")

    if "ket qua" in t:
        value = get_first(row, "KET_QUA", "KẾT_QUẢ")
        reply = f"✅ Kết quả - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "KET_QUA")

    if "co so phap ly" in t or "can cu phap ly" in t:
        value = get_first(row, "CO_SO_PHAP_LY", "CƠ_SỞ_PHÁP_LÝ")
        reply = f"⚖️ Cơ sở pháp lý - {ten}\n\n{compact(value, 1800)}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "CO_SO_PHAP_LY")

    if "link" in t or "dich vu cong" in t or "online" in t or "truc tuyen" in t:
        value = get_first(row, "LINK_DVC", "LINK")
        reply = f"🔗 Làm trực tuyến - {ten}\n\nQuý công dân có thể thực hiện trực tuyến qua Cổng Dịch vụ công nếu thủ tục được hỗ trợ.\n\n{value}" if value else format_thu_tuc(row)
        return reply + _faq_supplement_for_procedure(row, user_text, "LINK_DVC")

    if "buu dien" in t or "buu chinh" in t or "chuyen phat" in t or "gui ve nha" in t or "nhan tai nha" in t or "nhan ket qua" in t:
        value = get_first(row, "LUU_Y", "LƯU_Ý", "KET_QUA", "KẾT_QUẢ", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")
        reply = f"📦 Nhận kết quả - {ten}\n\n{compact(value, 1800)}" if value else f"📦 Nhận kết quả - {ten}\n\nChưa có dữ liệu riêng về nhận kết quả qua bưu điện trong Google Sheets."
        return reply + _faq_supplement_for_procedure(row, user_text, "KET_QUA")

    return format_thu_tuc(row)
    
# Chức năng: Chọn thủ tục từ danh sách gợi ý bằng số thứ tự.
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
# Vai trò: Khi đang ở một nhóm, BOT chỉ tìm trong đúng sheet hiện tại.
def _find_procedure_in_current_sheet(text, ctx):
    sheet = ctx.get("sheet", "")
    if not sheet or not sheet.startswith("THU_TUC_"):
        return None

    results = search_thu_tuc(text, limit=5, sheet=sheet)
    if not results:
        return None

    best = results[0]
    best_score = safe_int(best.get("_SCORE", 0))
    second_score = safe_int(results[1].get("_SCORE", 0)) if len(results) > 1 else 0
    if best_score >= 20 and best_score >= second_score + 8:
        return best
    return None


# Chức năng: Tạo lại danh sách thủ tục dựa trên context hiện tại.
# Vai trò: Dùng khi phân trang hoặc yêu cầu người dân chọn lại thủ tục.
def _procedure_list_reply_for_context(ctx):
    return _make_procedure_list_reply(ctx.get("sheet", ""), topic=ctx.get("topic", ""), page=ctx.get("page", 1))


# Chức năng: Tạo thông báo yêu cầu chọn thủ tục cụ thể.
# Vai trò: Tránh BOT đoán sai thủ tục khi câu hỏi chưa đủ rõ.
def _need_select_procedure_message(ctx):
    grouped = _procedure_list_reply_for_context(ctx)
    if grouped:
        reply, new_ctx = grouped
        return "Tôi chưa xác định được thủ tục cần chọn trong nhóm này.\n\n" + reply, new_ctx

    return _chat_setting("UNKNOWN_MESSAGE", "Tôi chưa xác định được thủ tục cần chọn. Quý công dân vui lòng nhập 'menu'."), ctx


# Chức năng: Tạo hướng dẫn tra cứu liên hệ từ SETTING_CHAT hoặc MENU.
# Vai trò: Không hardcode danh sách bộ phận liên hệ trong router.
def get_contact_lookup_message():
    configured = _chat_setting("CONTACT_GUIDE", "")
    if configured:
        return configured

    for row in _menu_rows():
        if normalize_text(get_first(row, "SHEET_DU_LIEU", "SHEET")) == "tra_cuu_lien_he":
            desc = get_first(row, "MO_TA", "MÔ_TẢ")
            return str(desc or "📌 Tra cứu liên hệ\n\nQuý công dân vui lòng nhập nội dung liên hệ cần tra cứu.").strip()

    return "📌 Tra cứu liên hệ\n\nQuý công dân vui lòng nhập nội dung liên hệ cần tra cứu."


# Chức năng: Xử lý kết quả liên hệ và câu nhắc làm rõ khi có nhiều kết quả.
# Vai trò: Chuẩn hóa trả lời TRA_CUU_LIEN_HE bằng dữ liệu sheet.
def _reply_contact_results(text, limit=5, keep_context=False):
    results = search_lien_he(text, limit=limit)
    if not results:
        return None

    reply = format_multiple_results(results, format_lien_he, limit=limit)
    if len(results) > 1:
        reply += "\n\nℹ️ Có nhiều kết quả phù hợp. Quý công dân vui lòng nhập rõ hơn họ tên, bộ phận hoặc địa bàn phụ trách để BOT tra cứu chính xác."

    ctx = {
        "stage": "contact_lookup" if keep_context else "",
        "sheet": "TRA_CUU_LIEN_HE",
        "topic": "Tra cứu liên hệ",
        "procedure_id": "",
        "procedure_name": "",
        "page": 1,
        "last_suggestions": [],
        "last_route": "TRA_CUU_LIEN_HE",
    }
    return reply, "TRA_CUU_LIEN_HE", ctx if keep_context else {}, ""


# Chức năng: Tìm thủ tục liên kết từ FAQ bằng RELATED_ID.
# Vai trò: Biến FAQ thành lớp hiểu ý định và dẫn về đúng thủ tục trong Google Sheets.
def _procedure_from_faq_related_id(faq_row):
    related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED", "MA_THU_TUC", "MÃ_THỦ_TỤC"))
    for related_id in related_ids:
        procedure = find_procedure_by_id(related_id)
        if procedure:
            return procedure
    return None


# Chức năng: Tìm MENU theo RELATED_ID hoặc dữ liệu mô tả của FAQ.
# Vai trò: Cho phép FAQ điều hướng về MENU.MO_TA khi NGU_CANH là MENU.
def _menu_from_faq(faq_row):
    related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED"))

    for rid in related_ids:
        rid_norm = normalize_text(rid)
        for row in _menu_rows():
            values = [
                get_first(row, "ID", "MA", "MÃ"),
                get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE"),
                get_first(row, "SHEET_DU_LIEU", "SHEET"),
            ]
            values.extend(_split_keywords(get_first(row, "TU_KHOA", "TỪ_KHÓA", "KEYWORDS")))

            if any(rid_norm and rid_norm == normalize_text(v) for v in values if v):
                return row

    lookup_text = " ".join([
        get_first(faq_row, "CHU_DE", "CHỦ_ĐỀ"),
        get_first(faq_row, "CAU_HOI", "CÂU_HỎI"),
        get_first(faq_row, "TU_KHOA", "TỪ_KHÓA", "KEYWORDS"),
    ]).strip()

    return _match_menu_by_data(lookup_text) if lookup_text else None


# Chức năng: Trả lời MENU theo NGU_CANH và RELATED_ID của FAQ.
# Vai trò: Trả về nội dung mô tả trong MENU, không hardcode nhóm phản ánh.
def _reply_menu_from_faq(faq_row):
    row = _menu_from_faq(faq_row)
    if not row:
        return None

    title = get_first(row, "TEN_CHUC_NANG", "TEN", "CHU_DE")
    desc = get_first(row, "MO_TA", "MÔ_TẢ")

    if desc:
        return f"📌 {title}\n\n{str(desc).strip()}" if title else str(desc).strip()

    reply, _suggestions = answer_from_menu(row)
    return reply


# Chức năng: Tìm dòng liên hệ theo danh sách RELATED_ID của FAQ.
# Vai trò: Điều hướng FAQ sang TRA_CUU_LIEN_HE bằng ID, bộ phận hoặc từ khóa trong Sheets.
def _lien_he_rows_by_related_ids(related_ids):
    results = []
    seen = set()

    for row in read_lien_he():
        if not _is_on(row):
            continue

        values = [
            get_first(row, "ID", "MA", "MÃ"),
            get_first(row, "BO_PHAN", "BỘ_PHẬN"),
            get_first(row, "TU_KHOA", "TỪ_KHÓA"),
            get_first(row, "CHUC_NANG", "CHỨC_NĂNG"),
            get_first(row, "CHUC_VU", "CHỨC_VỤ"),
            get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN"),
            get_first(row, "HO_TEN", "HỌ_TÊN"),
        ]

        values_norm = [normalize_text(v) for v in values if v]
        keyword_norm = []
        for value in values:
            keyword_norm.extend([normalize_text(x) for x in _split_keywords(value)])

        for rid in related_ids:
            rid_norm = normalize_text(rid)
            if not rid_norm:
                continue

            exact_match = any(rid_norm == v for v in values_norm + keyword_norm)
            contain_match = len(rid_norm) >= 4 and any(rid_norm in v for v in values_norm + keyword_norm)
            if exact_match or contain_match:
                key = normalize_text(get_first(row, "ID", "MA", "MÃ", "HO_TEN", "HỌ_TÊN"))
                if key not in seen:
                    results.append(row)
                    seen.add(key)
                break

    return results


# Chức năng: Trả lời liên hệ theo NGU_CANH và RELATED_ID của FAQ.
# Vai trò: Cho phép FAQ điều hướng sang TRA_CUU_LIEN_HE bằng dữ liệu Google Sheets.
def _reply_lien_he_from_faq(faq_row, user_text=""):
    related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED"))
    results = _lien_he_rows_by_related_ids(related_ids) if related_ids else []

    if not results and user_text:
        results = search_lien_he(user_text, limit=5) or []

    if not results:
        return get_contact_lookup_message()

    return format_multiple_results(results, format_lien_he, limit=5)


# Chức năng: Lấy giá trị THONGTIN theo KEY trong RELATED_ID của FAQ.
# Vai trò: Đọc đúng dữ liệu đơn vị từ sheet THONGTIN dù khác kiểu chữ.
def _thongtin_value(data, key):
    if not data or not key:
        return ""

    if key in data and data.get(key):
        return str(data.get(key)).strip()

    key_norm = normalize_text(key)
    for item_key, value in data.items():
        if normalize_text(item_key) == key_norm and value:
            return str(value).strip()

    return ""


# Chức năng: Trả lời thông tin đơn vị theo NGU_CANH và RELATED_ID của FAQ.
# Vai trò: Đọc các KEY trong sheet THONGTIN, không hardcode nghiệp vụ trong router.
def _reply_thongtin_from_faq(faq_row):
    related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED"))
    if not related_ids:
        return None

    data = read_thongtin() or {}
    lines = []

    for key in related_ids:
        value = _thongtin_value(data, key)
        if value:
            lines.append(value)

    if not lines:
        return None

    return "\n".join(lines)


# Chức năng: Tìm câu trả lời THONGTIN trong nhiều dòng FAQ.
# Vai trò: Bảo đảm câu hỏi thông tin đơn vị không bị TRA_CUU_LIEN_HE cướp luồng.
def _reply_thongtin_from_faq_rows(faq_rows):
    for faq_row in faq_rows or []:
        ngu_canh = normalize_text(get_first(faq_row, "NGU_CANH", "NGỮ_CẢNH"))
        if ngu_canh != "thongtin":
            continue

        reply = _reply_thongtin_from_faq(faq_row)
        if reply:
            return reply
    return None


# Chức năng: Tạo context thủ tục từ dòng thủ tục liên kết FAQ.
# Vai trò: Lưu đúng thủ tục đã nhận diện để xử lý câu hỏi nối tiếp.
def _context_from_related_procedure(procedure, ctx=None, route_name="FAQ_RELATED"):
    base_ctx = dict(ctx or {})
    return {
        "sheet": procedure.get("_SHEET", base_ctx.get("sheet", "")),
        "topic": get_first(procedure, "CHU_DE", "CHỦ_ĐỀ", default=base_ctx.get("topic", "")),
        "procedure_id": get_first(procedure, "ID", "MA", "MÃ"),
        "procedure_name": get_first(procedure, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
        "stage": "procedure",
        "page": 1,
        "last_suggestions": [],
        "last_route": route_name,
    }


# Chức năng: Định tuyến một dòng FAQ theo NGU_CANH và RELATED_ID.
# Vai trò: Ưu tiên ID liên kết; nếu ID rỗng thì trả theo ngữ cảnh của FAQ.
def _route_from_single_faq(user_text, faq_row, ctx):
    ngu_canh = normalize_text(get_first(faq_row, "NGU_CANH", "NGỮ_CẢNH"))
    related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED"))

    if not ngu_canh:
        return None

    if ngu_canh == "thongtin":
        reply = _reply_thongtin_from_faq(faq_row)
        if reply:
            new_ctx = dict(ctx or {})
            new_ctx["last_route"] = "FAQ_THONGTIN"
            return reply, "FAQ_THONGTIN", new_ctx, ""

    if ngu_canh == "tra_cuu_lien_he":
        reply = _reply_lien_he_from_faq(faq_row, user_text)
        new_ctx = {
            "stage": "contact_lookup" if not related_ids else "",
            "sheet": "TRA_CUU_LIEN_HE",
            "topic": "Tra cứu liên hệ",
            "procedure_id": "",
            "procedure_name": "",
            "page": 1,
            "last_suggestions": [],
            "last_route": "FAQ_TRA_CUU_LIEN_HE",
        }
        return reply, "FAQ_TRA_CUU_LIEN_HE", new_ctx if not related_ids else dict(ctx or {}), ""

    if ngu_canh == "menu":
        reply = _reply_menu_from_faq(faq_row)
        if reply:
            menu_row = _menu_from_faq(faq_row)
            new_ctx = menu_context(menu_row) if menu_row else dict(ctx or {})
            new_ctx["last_route"] = "FAQ_MENU"
            return reply, "FAQ_MENU", new_ctx, ""

    if ngu_canh == "procedure_context" and ctx.get("procedure_id"):
        procedure = find_procedure_by_id(ctx.get("procedure_id"))
        if procedure:
            new_ctx = dict(ctx or {})
            new_ctx["last_route"] = "FAQ_PROCEDURE_CONTEXT"
            return answer_procedure_detail(procedure, user_text), "FAQ_PROCEDURE_CONTEXT", new_ctx, ""

    if related_ids:
        procedure = _procedure_from_faq_related_id(faq_row)
        if procedure:
            new_ctx = _context_from_related_procedure(procedure, ctx, "FAQ_RELATED")
            if is_followup_detail_question(user_text):
                return answer_procedure_detail(procedure, user_text), "FAQ_RELATED", new_ctx, ""
            return format_thu_tuc(procedure), "FAQ_RELATED", new_ctx, ""

    return None



# Chức năng: Kiểm tra FAQ có đủ căn cứ để định tuyến sớm hay không.
# Vai trò: Cho FAQ ưu tiên các luồng có NGU_CANH rõ hoặc RELATED_ID, không cướp FAQ thường.
def _faq_has_action(faq_row, ctx=None):
    ngu_canh = normalize_text(get_first(faq_row, "NGU_CANH", "NGỮ_CẢNH"))
    related_ids = _split_keywords(get_first(faq_row, "RELATED_ID", "RELATED"))

    if related_ids:
        return True

    if ngu_canh in ["thongtin", "tra_cuu_lien_he", "menu"]:
        return True

    if ngu_canh == "procedure_context" and dict(ctx or {}).get("procedure_id"):
        return True

    return False

# Chức năng: Tạo context sạch khi BOT trả lời FAQ thường.
# Vai trò: Khi người dân đổi chủ đề sang FAQ, không giữ procedure_id của thủ tục cũ.
def _faq_plain_context(ctx, route="FAQ"):
    new_ctx = dict(ctx or {})
    new_ctx["last_route"] = route
    new_ctx["sheet"] = ""
    new_ctx["topic"] = ""
    new_ctx["procedure_id"] = ""
    new_ctx["procedure_name"] = ""
    new_ctx["stage"] = ""
    new_ctx["page"] = 1
    new_ctx["last_suggestions"] = []
    return new_ctx


# Chức năng: Kiểm tra có nên giữ ngữ cảnh thủ tục hiện tại hay không.
# Vai trò: Chỉ giữ context khi câu hỏi là chi tiết nối tiếp, không khóa chặt khi người dân đổi chủ đề.
def _should_keep_procedure_context(text, ctx, explicit=None):
    if not dict(ctx or {}).get("procedure_id"):
        return False
    if is_contact_question(text):
        return False
    if explicit:
        return False
    return is_followup_detail_question(text)


# Chức năng: Định tuyến danh sách FAQ theo NGU_CANH và RELATED_ID.
# Vai trò: Tập trung xử lý FAQ trước khi rơi về câu trả lời FAQ thường.
def _route_from_faq_rows(user_text, faq_rows, ctx):
    for faq_row in faq_rows or []:
        routed = _route_from_single_faq(user_text, faq_row, ctx)
        if routed:
            return routed

    normal_faq = _normal_faq_rows(faq_rows)
    if normal_faq:
        new_ctx = _faq_plain_context(ctx, "FAQ")
        return format_multiple_results(normal_faq[:1], format_faq, limit=1), "FAQ", new_ctx, ""

    if faq_rows:
        new_ctx = _faq_plain_context(ctx, "FAQ")
        return format_multiple_results(faq_rows[:1], format_faq, limit=1), "FAQ", new_ctx, ""

    return None


# Chức năng: Trả lời dữ liệu theo NGU_CANH và RELATED_ID của FAQ.
# Vai trò: Giữ tương thích cho vùng code cũ còn gọi _reply_by_faq_context.
def _reply_by_faq_context(faq_row):
    routed = _route_from_single_faq("", faq_row, {})
    return routed[0] if routed else None

# Chức năng: Định tuyến chính toàn bộ tin nhắn người dân.
# Vai trò: Ưu tiên THU_TUC_* theo TU_KHOA, FAQ chỉ bổ sung ý định trừ luồng VNeID/THONGTIN.
def route_message(user_text, context=None):
    ctx = dict(context or {})
    text = str(user_text or "").strip()
    text_norm = normalize_text(text)
    explicit = None

    if not text:
        return get_default_reply(), "EMPTY", ctx, ""

    if is_reset_question(text):
        return get_end_message(), "RESET", {}, ""

    if is_greeting(text):
        return get_welcome_message(), "WELCOME", {}, ""

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

    if text_norm.isdigit() and ctx.get("procedure_id"):
        procedure = find_procedure_by_id(ctx.get("procedure_id"))
        detail_map = {
            "1": "dieu kien",
            "2": "ho so",
            "3": "co quan thuc hien",
            "4": "thoi han",
            "5": "le phi",
            "6": "ket qua",
            "7": "co so phap ly",
        }
        if procedure and detail_map.get(text_norm):
            ctx["last_route"] = "PROCEDURE_CONTEXT"
            return answer_procedure_detail(procedure, detail_map[text_norm]), "PROCEDURE_CONTEXT", ctx, ""

    if text_norm.isdigit() and ctx.get("sheet", "").startswith("THU_TUC_") and not ctx.get("procedure_id"):
        reply, new_ctx = _need_select_procedure_message(ctx)
        new_ctx["last_route"] = "NEED_PROCEDURE_SELECT"
        return reply, "NEED_PROCEDURE_SELECT", new_ctx, ""

    if text_norm.isdigit():
        menu = _match_menu_by_number(text) or search_menu(text)
        if menu:
            reply, suggestions = answer_from_menu(menu)
            new_ctx = menu_context(menu)
            new_ctx["last_suggestions"] = suggestions
            new_ctx["last_route"] = "MENU"
            return reply, "MENU", new_ctx, ""

    faq = search_faq(text, limit=3)

    if not detect_bo_phan_contact(text):
        thongtin_reply = _reply_thongtin_from_faq_rows(faq)
        if thongtin_reply:
            ctx["last_route"] = "FAQ_THONGTIN"
            return thongtin_reply, "FAQ_THONGTIN", ctx, ""

    if is_contact_question(text):
        contact_reply = _reply_contact_results(text, limit=5, keep_context=False)
        if contact_reply:
            return contact_reply
        if _is_clear_contact_intent(text):
            new_ctx = {
                "stage": "contact_lookup",
                "sheet": "TRA_CUU_LIEN_HE",
                "topic": "Tra cứu liên hệ",
                "procedure_id": "",
                "procedure_name": "",
                "page": 1,
                "last_suggestions": [],
                "last_route": "CONTACT_GUIDE",
            }
            return get_contact_lookup_message(), "CONTACT_GUIDE", new_ctx, ""
    explicit = detect_explicit_topic(text)

    if _should_keep_procedure_context(text, ctx, explicit):
        procedure = find_procedure_by_id(ctx.get("procedure_id"))
        if procedure:
            ctx["last_route"] = "PROCEDURE_CONTEXT"
            return answer_procedure_detail(procedure, text), "PROCEDURE_CONTEXT", ctx, ""

    if faq and not is_contact_question(text) and not _should_keep_procedure_context(text, ctx, explicit):
        normal_faq = _normal_faq_rows(faq)
        if normal_faq:
            new_ctx = _faq_plain_context(ctx, "FAQ")
            return format_multiple_results(normal_faq[:1], format_faq, limit=1), "FAQ", new_ctx, ""

    actionable_faq = [row for row in faq or [] if _faq_has_action(row, ctx)]
    if actionable_faq:
        faq_routed = _route_from_faq_rows(text, actionable_faq, ctx)
        if faq_routed and faq_routed[1] != "FAQ":
            return faq_routed
    if explicit:
        explicit_sheet = explicit.get("sheet", "")
    
        candidate_results = search_thu_tuc(
            text,
            limit=5,
            sheet=explicit_sheet
        )
    
        if not candidate_results:
            candidate_results = _search_thu_tuc_by_tu_khoa(
                text,
                sheet=explicit_sheet,
                limit=5
            )

        if candidate_results:
            best = candidate_results[0]
            best_score = safe_int(best.get("_SCORE", 0))
            current_id = normalize_text(ctx.get("procedure_id"))
            best_id = normalize_text(get_first(best, "ID", "MA", "MÃ"))

            if best_score >= 45 and best_id and best_id != current_id:
                new_ctx = {
                    "sheet": best.get("_SHEET", ""),
                    "topic": get_first(best, "CHU_DE", "CHỦ_ĐỀ"),
                    "procedure_id": get_first(best, "ID", "MA", "MÃ"),
                    "procedure_name": get_first(best, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                    "stage": "procedure",
                    "page": 1,
                    "last_suggestions": [],
                    "last_route": "THU_TUC_TU_KHOA_OVERRIDE_CONTEXT",
                }
                return answer_procedure_detail(best, text), "THU_TUC_TU_KHOA_OVERRIDE_CONTEXT", new_ctx, ""

    if _should_keep_procedure_context(text, ctx, explicit):
        procedure = find_procedure_by_id(ctx.get("procedure_id"))
        if procedure:
            ctx["last_route"] = "PROCEDURE_CONTEXT"
            return answer_procedure_detail(procedure, text), "PROCEDURE_CONTEXT", ctx, ""

    if faq:
        faq_routed = _route_from_faq_rows(text, faq, ctx)
        if faq_routed:
            return faq_routed

    if ctx.get("stage") == "contact_lookup":
        contact_reply = _reply_contact_results(text, limit=5, keep_context=True)
        if contact_reply:
            return contact_reply
        ctx["last_route"] = "CONTACT_NOT_FOUND"
        return _chat_setting(
            "CONTACT_NOT_FOUND",
            "Chưa tìm thấy thông tin liên hệ phù hợp. Quý công dân vui lòng nhập rõ hơn họ tên, bộ phận hoặc địa bàn phụ trách."
        ), "CONTACT_NOT_FOUND", ctx, ""

    if is_contact_question(text):
        contact_reply = _reply_contact_results(text, limit=5, keep_context=False)
        if contact_reply:
            return contact_reply
    menu_row = _match_menu_by_data(text)
    if menu_row and normalize_text(get_first(menu_row, "SHEET_DU_LIEU", "SHEET")) == "tra_cuu_lien_he":
        new_ctx = menu_context(menu_row)
        new_ctx["last_route"] = "MENU"
        return get_contact_lookup_message(), "MENU", new_ctx, ""

    if explicit:
        explicit_sheet = explicit.get("sheet", "")
        explicit_topic = explicit.get("topic", "")

        if normalize_text(explicit_sheet) not in ["faq", "thu_tuc_vneid"]:
            if is_group_only_topic_request(text, explicit):
                grouped = _make_procedure_list_reply(explicit_sheet, topic=explicit_topic, page=1)
                if grouped:
                    reply, new_ctx = grouped
                    new_ctx["last_route"] = "MENU_GROUP"
                    return reply, "MENU_GROUP", new_ctx, ""

        if normalize_text(explicit_sheet) in ["faq", "thu_tuc_vneid"]:
            if faq:
                context_reply = _reply_by_faq_context(faq[0])
                if context_reply:
                    ctx["last_route"] = "FAQ_CONTEXT"
                    return context_reply, "FAQ_CONTEXT", ctx, ""

                normal_faq = _normal_faq_rows(faq)
                if normal_faq:
                    ctx["last_route"] = "FAQ"
                    return format_multiple_results(normal_faq[:1], format_faq, limit=1), "FAQ", ctx, ""

                related_procedure = _procedure_from_faq_related_id(faq[0])
                if related_procedure:
                    new_ctx = {
                        "sheet": related_procedure.get("_SHEET", explicit_sheet),
                        "topic": get_first(related_procedure, "CHU_DE", "CHỦ_ĐỀ", default=explicit_topic),
                        "procedure_id": get_first(related_procedure, "ID", "MA", "MÃ"),
                        "procedure_name": get_first(related_procedure, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                        "stage": "procedure",
                        "page": 1,
                        "last_suggestions": [],
                        "last_route": "FAQ_RELATED",
                    }
                    if is_followup_detail_question(text):
                        return answer_procedure_detail(related_procedure, text), "FAQ_RELATED", new_ctx, ""
                    return format_thu_tuc(related_procedure), "FAQ_RELATED", new_ctx, ""

            if normalize_text(explicit_sheet) == "faq":
                ctx["last_route"] = "FAQ_NOT_FOUND"
                return get_default_reply(), "FAQ_NOT_FOUND", ctx, ""

            procedure_results = search_thu_tuc(text, limit=5, sheet=explicit_sheet)
        else:
            procedure_results = _search_thu_tuc_by_tu_khoa(text, sheet=explicit_sheet, limit=5)

        if procedure_results:
            best = procedure_results[0]
            best_score = safe_int(best.get("_SCORE", 0))
            second_score = safe_int(procedure_results[1].get("_SCORE", 0)) if len(procedure_results) > 1 else 0

            if best_score >= 35 and best_score >= second_score + 8:
                new_ctx = {
                    "sheet": best.get("_SHEET", explicit_sheet),
                    "topic": get_first(best, "CHU_DE", "CHỦ_ĐỀ", default=explicit_topic),
                    "procedure_id": get_first(best, "ID", "MA", "MÃ"),
                    "procedure_name": get_first(best, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                    "stage": "procedure",
                    "page": 1,
                    "last_suggestions": [],
                    "last_route": "THU_TUC_TU_KHOA" if not _is_vneid_sheet(explicit_sheet) else "THU_TUC_VNEID",
                }
                if is_followup_detail_question(text):
                    return answer_procedure_detail(best, text), new_ctx["last_route"], new_ctx, ""
                return format_thu_tuc(best), new_ctx["last_route"], new_ctx, ""

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
                "last_route": "CLARIFY_THU_TUC_TU_KHOA",
            }
            return "Tôi tìm thấy một số thủ tục gần giống trong nhóm này. Quý công dân vui lòng chọn số tương ứng:\n\n" + "\n".join(lines), "CLARIFY_THU_TUC_TU_KHOA", new_ctx, ""

        grouped = _make_procedure_list_reply(explicit_sheet, topic=explicit_topic, page=1)
        if grouped:
            reply, new_ctx = grouped
            new_ctx["last_route"] = "MENU_GROUP"
            return reply, "MENU_GROUP", new_ctx, ""

    if ctx.get("sheet", "").startswith("THU_TUC_") and not ctx.get("procedure_id"):
        if is_next_page_question(text):
            next_ctx = dict(ctx)
            next_ctx["page"] = safe_int(ctx.get("page", 1), default=1) + 1
            grouped = _procedure_list_reply_for_context(next_ctx)
            if grouped:
                reply, new_ctx = grouped
                new_ctx["last_route"] = "PROCEDURE_LIST_NEXT"
                return reply, "PROCEDURE_LIST_NEXT", new_ctx, ""

        sheet = ctx.get("sheet", "")
        if _is_vneid_sheet(sheet):
            procedure = _find_procedure_in_current_sheet(text, ctx)
        else:
            results = _search_thu_tuc_by_tu_khoa(text, sheet=sheet, limit=5)
            procedure = results[0] if results and safe_int(results[0].get("_SCORE", 0)) >= 35 else None

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
            if is_followup_detail_question(text):
                return answer_procedure_detail(procedure, text), "THU_TUC_IN_CONTEXT", new_ctx, ""
            return format_thu_tuc(procedure), "THU_TUC_IN_CONTEXT", new_ctx, ""

        reply, new_ctx = _need_select_procedure_message(ctx)
        new_ctx["last_route"] = "NEED_PROCEDURE_SELECT"
        return reply, "NEED_PROCEDURE_SELECT", new_ctx, ""

    menu = _match_menu_by_data(text)
    if menu:
        reply, suggestions = answer_from_menu(menu)
        new_ctx = menu_context(menu)
        new_ctx["last_suggestions"] = suggestions
        new_ctx["last_route"] = "MENU"
        return reply, "MENU", new_ctx, ""

    thu_tuc_results = _search_thu_tuc_by_tu_khoa(text, sheet=None, limit=5)
    if thu_tuc_results:
        best = thu_tuc_results[0]
        best_score = safe_int(best.get("_SCORE", 0))
        second_score = safe_int(thu_tuc_results[1].get("_SCORE", 0)) if len(thu_tuc_results) > 1 else 0

        if best_score >= 45 and best_score >= second_score + 15:
            new_ctx = {
                "sheet": best.get("_SHEET", ""),
                "topic": get_first(best, "CHU_DE", "CHỦ_ĐỀ"),
                "procedure_id": get_first(best, "ID", "MA", "MÃ"),
                "procedure_name": get_first(best, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
                "stage": "procedure",
                "page": 1,
                "last_suggestions": [],
                "last_route": "THU_TUC_TU_KHOA_GLOBAL",
            }
            if is_followup_detail_question(text):
                return answer_procedure_detail(best, text), "THU_TUC_TU_KHOA_GLOBAL", new_ctx, ""
            return format_thu_tuc(best), "THU_TUC_TU_KHOA_GLOBAL", new_ctx, ""

    normal_faq = _normal_faq_rows(faq)
    if normal_faq:
        ctx["last_route"] = "FAQ"
        return format_multiple_results(normal_faq, format_faq, limit=3), "FAQ", ctx, ""

    ctx["last_route"] = "DEFAULT"
    print("===== DEFAULT REACHED =====")
    print("QUESTION:", user_text)
    print("===========================")
    return get_default_reply(), "DEFAULT", ctx, ""
    
# Chức năng: Định tuyến tin nhắn người dân, chuẩn hóa kết quả trả về cho app.py.
# Vai trò: Ưu tiên Google Sheets, chỉ bật Gemini như lớp phụ trợ tùy chọn.
def route_message_for_ai(user_text, context=None):
    result = {
        "reply": get_default_reply(),
        "source": "DEFAULT",
        "use_ai": False,
        "context": dict(context or {}),
        "ai_context": "",
        "ai_mode": _ai_setting("AI_MODE", "OPTIONAL"),
    }

    try:
        reply, source, new_context, ai_context = route_message(user_text=user_text, context=context)
        result["reply"] = reply
        result["source"] = source
        result["context"] = new_context
        result["ai_context"] = ai_context
        result["use_ai"] = _should_use_ai(user_text, source, ai_context)

        if source == "DEFAULT" and not result["use_ai"]:
            result["unknown_log"] = True

    except Exception as e:
        print(f"[ROUTER ERROR] {e}")
        result["reply"] = get_default_reply()
        result["source"] = "ROUTER_ERROR"
        result["use_ai"] = _should_use_ai(user_text, "ROUTER_ERROR", "")
        result["context"] = dict(context or {})
        result["ai_context"] = ""
        result["unknown_log"] = not result["use_ai"]

    return result
