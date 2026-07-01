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
    results = []
    for row in read_lien_he():
        score = 0
        score += keyword_score(user_text, get_first(row, "TU_KHOA", "TỪ_KHÓA"), 5)
        score += phrase_score(user_text, get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN"), 4)
        score += phrase_score(user_text, get_first(row, "BO_PHAN", "BỘ_PHẬN", "CHUC_NANG", "CHỨC_NĂNG"), 3)
        score += phrase_score(user_text, get_first(row, "TDP", "GHI_CHU", "GHI_CHÚ"), 1)
        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            results.append(row)
    results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
    return results[:limit]


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


def format_thu_tuc(row):
    ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
    doi_tuong = get_first(row, "DOI_TUONG_AP_DUNG", "ĐỐI_TƯỢNG_ÁP_DỤNG")
    ho_so = get_first(row, "HO_SO", "HỒ_SƠ")
    noi_nop = get_first(row, "NOI_NOP", "NƠI_NỘP", "CO_QUAN_THUC_HIEN", "CƠ_QUAN_THỰC_HIỆN")
    thoi_han = get_first(row, "THOI_HAN", "THỜI_HẠN")
    le_phi = get_first(row, "LE_PHI", "LỆ_PHÍ", "PHI")
    parts = [f"📌 {ten}" if ten else "📌 Thông tin thủ tục"]
    if doi_tuong: parts.append(f"👤 Đối tượng:\n{compact(doi_tuong, 500)}")
    if ho_so: parts.append(f"📄 Hồ sơ:\n{compact(ho_so, 800)}")
    if noi_nop: parts.append(f"📍 Cơ quan/nơi tiếp nhận:\n{compact(noi_nop, 500)}")
    if thoi_han: parts.append(f"⏱ Thời hạn: {thoi_han}")
    if le_phi: parts.append(f"💰 Lệ phí: {le_phi}")
    parts.append("————————————\nBạn có thể hỏi tiếp: hồ sơ chi tiết, trình tự, cơ quan tiếp nhận, thời hạn, lệ phí, cơ sở pháp lý, link dịch vụ công.")
    return "\n\n".join(parts)


def format_multiple_results(results, formatter, limit=3):
    texts = []
    for i, row in enumerate(results[:limit], start=1):
        val = formatter(row)
        if val:
            texts.append(f"{i}. {val}")
    return "\n\n".join(texts)
