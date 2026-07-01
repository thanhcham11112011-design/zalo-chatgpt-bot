import re
from services.sheet_api import read_menu, read_lien_he, read_faq, read_all_thu_tuc
from services.text_utils import normalize_text, get_first, safe_int, split_keywords, compact


def keyword_score(user_text, keywords, weight=1):
    user_norm = normalize_text(user_text)
    if not user_norm:
        return 0
    score = 0
    for kw in split_keywords(keywords):
        if kw and kw in user_norm:
            score += max(len(kw), 2) * weight
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


def search_lien_he(user_text, limit=3):
    """
    BOT V2.2 - Tra cứu liên hệ theo 3 tầng ưu tiên:

    1. Ưu tiên khớp TEN_CO_QUAN nếu người dân nêu rõ tên cơ quan.
    2. Nếu không có, khớp TU_KHOA.
    3. Nếu không có, khớp CHUC_NANG / GHI_CHU / BO_PHAN / TDP.

    Mục tiêu:
    - "Công an phường Phù Liễn ở đâu" chỉ trả Công an phường Phù Liễn.
    - Không trả lẫn Công an phường Kiến An.
    """

    rows = read_lien_he()
    text_norm = normalize_text(user_text)

    if not text_norm:
        return []

    # =========================
    # TẦNG 1: KHỚP TÊN CƠ QUAN
    # =========================

    exact_name_results = []
    partial_name_results = []

    for row in rows:
        ten_co_quan = get_first(
            row,
            "TEN_CO_QUAN",
            "TÊN_CƠ_QUAN",
            "HO_TEN",
            "HỌ_TÊN"
        )

        ten_norm = normalize_text(ten_co_quan)

        if not ten_norm:
            continue

        # Khớp chính xác toàn bộ tên cơ quan
        if ten_norm == text_norm:
            row["_SCORE"] = 10000
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            exact_name_results.append(row)
            continue

        # Người dân hỏi: "Công an phường Phù Liễn ở đâu"
        # ten_norm = "cong an phuong phu lien"
        # text_norm chứa ten_norm => trả đúng cơ quan này
        if ten_norm in text_norm:
            row["_SCORE"] = 9000 + len(ten_norm)
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            partial_name_results.append(row)

    if exact_name_results:
        exact_name_results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))
        return exact_name_results[:limit]

    if partial_name_results:
        partial_name_results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))
        return partial_name_results[:limit]

    # =========================
    # TẦNG 2: KHỚP TỪ KHÓA
    # =========================

    keyword_results = []

    for row in rows:
        score = field_score(
            user_text,
            get_first(row, "TU_KHOA", "TỪ_KHÓA")
        )

        if score > 0:
            row["_SCORE"] = 5000 + score
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            keyword_results.append(row)

    if keyword_results:
        keyword_results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))
        return keyword_results[:limit]

    # =========================
    # TẦNG 3: KHỚP CHỨC NĂNG / GHI CHÚ
    # =========================

    fallback_results = []

    for row in rows:
        score = field_score(
            user_text,
            get_first(row, "CHUC_NANG", "CHỨC_NĂNG"),
            get_first(row, "GHI_CHU", "GHI_CHÚ"),
            get_first(row, "BO_PHAN", "BỘ_PHẬN"),
            get_first(row, "TDP")
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            fallback_results.append(row)

    fallback_results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))

    return fallback_results[:limit]

def search_thu_tuc(user_text, limit=5, sheet=None):
    results = []
    for row in read_all_thu_tuc():
        if sheet and row.get("_SHEET") != sheet:
            continue
        score = 0
        score += keyword_score(user_text, get_first(row, "TU_KHOA", "TỪ_KHÓA"), 6)
        score += phrase_score(user_text, get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC"), 5)
        score += phrase_score(user_text, get_first(row, "CHU_DE", "CHỦ_ĐỀ"), 3)
        score += phrase_score(user_text, get_first(row, "MO_TA", "MÔ_TẢ", "GOI_Y_CAU_HOI", "GỢI_Ý_CÂU_HỎI"), 2)
        score += phrase_score(user_text, get_first(row, "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN"), 1)
        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", default=999))
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
