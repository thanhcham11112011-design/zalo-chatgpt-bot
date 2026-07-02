import re
from services.sheet_api import read_menu, read_lien_he, read_faq, read_all_thu_tuc
from services.text_utils import normalize_text, get_first, safe_int, split_keywords, compact

def detect_bo_phan_contact(user_text):
    t = normalize_text(user_text)

    if "chi huy" in t or "lanh dao" in t:
        return "CHI_HUY"

    if "cskv" in t or "canh sat khu vuc" in t:
        return "CSKV"

    if "an ninh" in t:
        return "AN_NINH"

    if "pctp" in t or "phong chong toi pham" in t:
        return "PCTP"

    if "cstt" in t or "canh sat trat tu" in t:
        return "CSTT"

    if t in ["th", "tong hop", "to tong hop"]:
        return "TH"

    return ""
    
def keyword_score(user_text, keywords, weight=1):
    user_norm = normalize_text(user_text)
    if not user_norm:
        return 0
    score = 0
    for kw in split_keywords(keywords):
        if kw and kw in user_norm:
            score += max(len(kw), 2) * weight
    return score
def field_score(user_text, *fields):
    score = 0

    for field in fields:
        score += keyword_score(user_text, field)

    return score

def phrase_score(user_text, value, weight=1):
    user_norm = normalize_text(user_text)
    value_norm = normalize_text(value)
    if not user_norm or not value_norm:
        return 0
    score = 0
    if user_norm == value_norm:
        score += 100 * weight
    if user_norm in value_norm or value_norm in user_norm:
        score += 30 * weight
    for token in user_norm.split():
        if len(token) >= 2 and token in value_norm:
            score += 2 * weight
    return score


def search_menu(user_text):
    user_norm = normalize_text(user_text)
    results = []
    for row in read_menu():
        menu_id = str(row.get("ID", "")).strip()
        title = get_first(row, "TEN_CHUC_NANG", "TÊN_CHỨC_NĂNG", "TEN", "CHU_DE", "MO_TA", "MÔ_TẢ")
        keywords = get_first(row, "TU_KHOA", "TỪ_KHÓA", "TU KHOA")
        desc = get_first(row, "MO_TA", "MÔ_TẢ")
        score = 0
        if user_norm == normalize_text(menu_id):
            score += 1000
        score += keyword_score(user_text, keywords, 4)
        score += phrase_score(user_text, title, 3)
        score += phrase_score(user_text, desc, 1)
        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            results.append(row)
    results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
    return results[0] if results else None


def _agency_base_name(name):
    text = normalize_text(name)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\bco so\s*\d+\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _keyword_exact_match(user_text, keywords):
    user_norm = normalize_text(user_text)
    for kw in split_keywords(keywords):
        kw_norm = normalize_text(kw)
        if kw_norm and kw_norm in user_norm:
            return True
    return False


def search_lien_he(user_text, limit=3):
    rows = read_lien_he()
    text_norm = normalize_text(user_text)

    if not text_norm:
        return []
    bo_phan = detect_bo_phan_contact(user_text)

    if bo_phan:
        results = []

        for row in rows:
            row_bo_phan = normalize_text(get_first(row, "BO_PHAN", "BỘ_PHẬN"))
            trang_thai = normalize_text(get_first(row, "TRANG_THAI", "TRẠNG_THÁI"))

            if trang_thai == "off":
                continue

            if row_bo_phan == normalize_text(bo_phan):
                row["_SCORE"] = 10000
                row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
                results.append(row)

        results.sort(key=lambda r: (r["_UU_TIEN"], get_first(r, "TEN_CO_QUAN", "HỌ_TÊN", "HO_TEN")))
        return results[:limit]

    # TẦNG 1: nếu câu hỏi nêu rõ tên cơ quan
    name_results = []

    for row in rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        ten_norm = normalize_text(ten)
        base_norm = _agency_base_name(ten)

        if not ten_norm:
            continue

        if ten_norm in text_norm or base_norm in text_norm:
            row["_SCORE"] = 10000 + len(base_norm)
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            name_results.append(row)

    if name_results:
        name_results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
        return name_results[:limit]

    # TẦNG 2: khớp từ khóa rõ ràng trong TU_KHOA
    keyword_results = []

    for row in rows:
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")

        if _keyword_exact_match(user_text, tu_khoa):
            row["_SCORE"] = 8000 + keyword_score(user_text, tu_khoa, 5)
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            keyword_results.append(row)

    if keyword_results:
        keyword_results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
        return keyword_results[:limit]

    # TẦNG 3: tìm rộng khi không có tên cơ quan/từ khóa rõ
    fallback_results = []

    for row in rows:
        score = 0
        score += phrase_score(user_text, get_first(row, "CHUC_NANG", "CHỨC_NĂNG"), 3)
        score += phrase_score(user_text, get_first(row, "GHI_CHU", "GHI_CHÚ"), 1)
        score += phrase_score(user_text, get_first(row, "BO_PHAN", "BỘ_PHẬN"), 1)
        score += phrase_score(user_text, get_first(row, "TDP"), 1)

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            fallback_results.append(row)

    fallback_results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
    return fallback_results[:limit]


def search_faq(user_text, limit=3):
    results = []
    for row in read_faq():
        score = 0
        score += keyword_score(user_text, get_first(row, "TU_KHOA", "TỪ_KHÓA"), 5)
        score += phrase_score(user_text, get_first(row, "CAU_HOI", "CÂU_HỎI"), 4)
        score += phrase_score(user_text, get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRA_LOI_DAY_DU"), 1)
        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            results.append(row)
    results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
    return results[:limit]


def search_thu_tuc(user_text, limit=5, sheet=None):
    """
    BOT V2.2:
    Chỉ tìm thủ tục khi câu hỏi khớp rõ TU_KHOA hoặc TEN_THU_TUC.
    Câu ngoài luồng sẽ không bị bắt nhầm, để chuyển Gemini xử lý.
    """
    results = []
    user_norm = normalize_text(user_text)

    if not user_norm:
        return []

    for row in read_all_thu_tuc():
        if sheet and row.get("_SHEET") != sheet:
            continue

        score = 0

        keyword = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")

        keyword_match = keyword_score(user_text, keyword, 8)
        title_match = phrase_score(user_text, ten, 6)

        score += keyword_match
        score += title_match

        # Không cộng điểm lan man nếu không khớp từ khóa hoặc tên thủ tục
        if keyword_match <= 0 and title_match < 30:
            continue

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(
                get_first(row, "MUC_UU_TIEN", "UU_TIEN", default=999)
            )
            results.append(row)

    results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
    return results[:limit]


def list_procedures_by_sheet(sheet, limit=10):
    rows = []
    for row in read_all_thu_tuc():
        if row.get("_SHEET") == sheet:
            row["_UU_TIEN"] = safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", default=999))
            rows.append(row)
    rows.sort(key=lambda r: r["_UU_TIEN"])
    return rows[:limit]


def find_procedure_by_id(procedure_id):
    pid = str(procedure_id or "").strip()
    if not pid:
        return None
    for row in read_all_thu_tuc():
        if str(row.get("ID", "")).strip() == pid:
            return row
    return None


def format_lien_he(row):
    parts = []
    ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HỌ_TÊN", "HO_TEN")
    chuc = get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHUC_VU", "CHỨC_VỤ")
    bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")
    phone = get_first(row, "SO_DIEN_THOAI", "ĐIỆN_THOẠI", "DIEN_THOAI", "PHONE")
    address = get_first(row, "DIA_CHI", "ĐỊA_CHỈ", "ADDRESS")
    note = get_first(row, "GHI_CHU", "GHI_CHÚ")
    map_link = get_first(row, "GOOGLE_MAP", "MAP")
    if ten: parts.append(f"📌 {ten}")
    if chuc: parts.append(f"Chức năng: {chuc}")
    if bo_phan: parts.append(f"Bộ phận: {bo_phan}")
    if address: parts.append(f"Địa chỉ: {address}")
    if phone: parts.append(f"Điện thoại: {phone}")
    if note: parts.append(f"Ghi chú: {note}")
    if map_link: parts.append(f"Bản đồ: {map_link}")
    return "\n".join(parts)


def format_faq(row):
    q = get_first(row, "CAU_HOI", "CÂU_HỎI")
    a = get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")
    return f"❓ {q}\n\n{a}" if q and a else (a or q)


def _short_steps(value, max_len=700):
    """Rút gọn quy trình/trình tự ở phần trả lời đầu."""
    text = compact(value, max_len)
    if not text:
        return ""

    # Nếu nội dung có nhiều bước, chỉ giữ gọn để tin nhắn không quá dài.
    lower = normalize_text(text)
    if "buoc" in lower:
        return text

    return text


def format_thu_tuc(row):
    """
    BOT V2.1 - Mẫu trả lời thủ tục thống nhất:
    1. Đối tượng
    2. Hồ sơ
    3. Quy trình thực hiện
    4. Link DVC
    5. Lời nhắc hỏi tiếp
    """
    ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
    doi_tuong = get_first(row, "DOI_TUONG_AP_DUNG", "ĐỐI_TƯỢNG_ÁP_DỤNG")
    ho_so = get_first(row, "HO_SO", "HỒ_SƠ")
    quy_trinh = get_first(row, "TRINH_TU", "TRÌNH_TỰ", "QUY_TRINH", "QUY_TRÌNH")
    link_dvc = get_first(row, "LINK_DVC", "LINK", "DICH_VU_CONG", "DỊCH_VỤ_CÔNG")

    parts = [f"📌 {ten}" if ten else "📌 Thông tin thủ tục"]

    if doi_tuong:
        parts.append(f"👤 Đối tượng:\n{compact(doi_tuong, 500)}")
    else:
        parts.append("👤 Đối tượng:\nTheo quy định đối với từng trường hợp cụ thể.")

    if ho_so:
        parts.append(f"📄 Hồ sơ:\n{compact(ho_so, 700)}")
    else:
        parts.append("📄 Hồ sơ:\nCông dân chuẩn bị hồ sơ theo hướng dẫn của cơ quan tiếp nhận.")

    if quy_trinh:
        parts.append(f"📝 Quy trình thực hiện:\n{_short_steps(quy_trinh, 700)}")
    else:
        parts.append("📝 Quy trình thực hiện:\nCông dân nộp hồ sơ, cơ quan có thẩm quyền tiếp nhận, kiểm tra, xử lý và trả kết quả theo quy định.")

    if link_dvc:
        parts.append(f"🔗 LINK DVC:\n{link_dvc}")
    else:
        parts.append("🔗 LINK DVC:\nChưa có link dịch vụ công trong dữ liệu. Công dân có thể tra cứu trên Cổng Dịch vụ công hoặc liên hệ cơ quan tiếp nhận để được hướng dẫn.")

    parts.append(
        "————————————\n"
        "💬 Bạn có thể hỏi tiếp: hồ sơ chi tiết, trình tự, cơ quan tiếp nhận, thời hạn, lệ phí, cơ sở pháp lý."
    )

    return "\n\n".join(parts)

def format_multiple_results(results, formatter, limit=3):
    texts = []
    for i, row in enumerate(results[:limit], start=1):
        val = formatter(row)
        if val:
            texts.append(f"{i}. {val}")
    return "\n\n".join(texts)
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
        if name_norm in normalize_text(ten) or normalize_text(ten) in name_norm:
            return row

    return None
