import re
from services.sheet_api import read_menu, read_lien_he, read_faq, read_all_thu_tuc
from services.text_utils import normalize_text, get_first, safe_int, split_keywords, compact


# Chức năng: Nhận diện bộ phận liên hệ từ nội dung người dân nhập.
# Vai trò: Giúp BOT lọc đúng bộ phận trước khi chấm điểm, tránh trả lẫn cán bộ không liên quan.
# Chức năng: Nhận diện bộ phận liên hệ từ nội dung người dân nhập.
# Vai trò: Giúp BOT lọc đúng bộ phận trước khi chấm điểm, tránh trả lẫn cán bộ không liên quan.
def detect_bo_phan_contact(user_text):
    t = normalize_text(user_text)

    truc_ban_keys = [
        "so dien thoai cong an phuong",
        "dien thoai cong an phuong",
        "sdt cong an phuong",
        "so truc ban",
        "dien thoai truc ban",
        "sdt truc ban",
        "truc ban",
        "hotline",
        "duong day nong",
        "tiep nhan tin bao",
        "to giac toi pham",
        "phan anh antt",
        "bao tin",
    ]

    if any(k in t for k in truc_ban_keys):
        return "TRUC_BAN"

    has_chi_huy = any(k in t for k in [
        "chi huy",
        "lanh dao",
        "ban chi huy",
        "truong cap",
        "pho truong cap"
    ])

    has_pctp = any(k in t for k in [
        "pctp",
        "phong chong toi pham",
        "chong toi pham",
        "toi pham",
        "hinh su"
    ])

    if has_chi_huy:
        return "CHI_HUY"

    if has_pctp:
        return "PCTP"

    if any(k in t for k in [
        "cskv",
        "canh sat khu vuc",
        "can bo khu vuc",
        "phu trach dia ban"
    ]):
        return "CSKV"

    if any(k in t for k in [
        "an ninh",
        "to an ninh",
        "can bo an ninh"
    ]):
        return "AN_NINH"

    if any(k in t for k in [
        "cstt",
        "canh sat trat tu",
        "trat tu"
    ]):
        return "CSTT"

    if any(k in t for k in [
        "cntt",
        "cong nghe thong tin",
        "chuyen doi so"
    ]):
        return "CNTT"

    if any(k in t for k in [
        "doan thanh nien",
        "dtn"
    ]):
        return "DOAN_THANH_NIEN"

    if any(k in t for k in [
        "tong hop",
        "to tong hop",
        "doi tong hop",
        "bo phan tong hop",
        "can bo tong hop"
    ]):
        return "TH"

    if any(k in t for k in [
        "dia chi",
        "google map",
        "ban do",
        "co quan",
        "co so 1",
        "co so 2"
    ]):
        return "CO_QUAN"

    return ""
# Chức năng: Chấm điểm khớp từ khóa giữa câu hỏi người dân và chuỗi từ khóa trong Sheet.
# Đầu vào: user_text - câu hỏi; keywords - chuỗi từ khóa; weight - trọng số điểm.
# Đầu ra: Điểm số khớp từ khóa.
# Vai trò: Là nền tảng chấm điểm cho menu, liên hệ, FAQ và thủ tục.
def keyword_score(user_text, keywords, weight=1):
    user_norm = normalize_text(user_text)
    if not user_norm:
        return 0

    score = 0
    for kw in split_keywords(keywords):
        if kw and kw in user_norm:
            score += max(len(kw), 2) * weight
    return score


# Chức năng: Chấm điểm nhiều trường dữ liệu theo cùng cơ chế từ khóa.
# Đầu vào: user_text - câu hỏi; fields - các trường cần chấm điểm.
# Đầu ra: Tổng điểm khớp từ khóa.
# Vai trò: Hỗ trợ gom điểm từ nhiều cột dữ liệu khi tìm kiếm.
def field_score(user_text, *fields):
    score = 0

    for field in fields:
        score += keyword_score(user_text, field)

    return score


# Chức năng: Chấm điểm khớp cụm từ giữa câu hỏi và một giá trị dữ liệu.
# Đầu vào: user_text - câu hỏi; value - giá trị cần so khớp; weight - trọng số.
# Đầu ra: Điểm số khớp cụm từ.
# Vai trò: Giúp BOT tìm theo tên cơ quan, tên thủ tục, mô tả hoặc chức năng.
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


# Chức năng: Tìm chức năng menu phù hợp với nội dung người dân nhập.
# Đầu vào: user_text - câu hỏi hoặc số menu.
# Đầu ra: Dòng MENU phù hợp nhất hoặc None.
# Vai trò: Định tuyến nhóm chức năng chính của BOT.
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


# Chức năng: Chuẩn hóa tên cơ quan về tên gốc để so khớp rộng.
# Đầu vào: name - tên cơ quan.
# Đầu ra: Tên cơ quan đã bỏ phần trong ngoặc, cơ sở và khoảng trắng thừa.
# Vai trò: Giúp BOT nhận diện tên cơ quan ngay cả khi người dân nhập thiếu phần mô tả.
def _agency_base_name(name):
    text = normalize_text(name)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\bco so\s*\d+\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Chức năng: Kiểm tra câu hỏi có khớp rõ một từ khóa trong cột TU_KHOA hay không.
# Đầu vào: user_text - câu hỏi; keywords - chuỗi từ khóa trong Sheet.
# Đầu ra: True nếu có từ khóa khớp, False nếu không.
# Vai trò: Tầng lọc chính xác trước khi tìm kiếm rộng.
def _keyword_exact_match(user_text, keywords):
    user_norm = normalize_text(user_text)
    for kw in split_keywords(keywords):
        kw_norm = normalize_text(kw)
        if kw_norm and kw_norm in user_norm:
            return True
    return False


# Chức năng: Tìm thông tin liên hệ trong sheet TRA_CUU_LIEN_HE.
# Vai trò: Tra cứu cán bộ, bộ phận, cơ quan, trực ban, địa chỉ, số điện thoại từ Google Sheets.
def search_lien_he(user_text, limit=3):
    rows = read_lien_he()
    text_raw = str(user_text or "").lower()
    text_norm = normalize_text(user_text)

    if not text_norm:
        return []

    active_rows = []
    for row in rows:
        trang_thai = normalize_text(get_first(row, "TRANG_THAI", "TRẠNG_THÁI"))
        if trang_thai != "off":
            active_rows.append(row)

    bo_phan = detect_bo_phan_contact(user_text)

    if not bo_phan and any(k in text_norm for k in ["tong hop", "to tong hop", "doi tong hop"]):
        bo_phan = "TH"

    search_rows = active_rows
    if bo_phan:
        search_rows = []
        for row in active_rows:
            row_bo_phan_norm = normalize_text(get_first(row, "BO_PHAN", "BỘ_PHẬN"))
            row_chuc_nang_norm = normalize_text(get_first(row, "CHUC_NANG", "CHỨC_NĂNG"))
            row_tu_khoa_norm = normalize_text(get_first(row, "TU_KHOA", "TỪ_KHÓA"))

            if row_bo_phan_norm == normalize_text(bo_phan):
                search_rows.append(row)
            elif normalize_text(bo_phan) == "th" and (
                "tong hop" in row_chuc_nang_norm or "tong hop" in row_tu_khoa_norm
            ):
                search_rows.append(row)

    name_results = []

    clean_text_raw = text_raw
    for ch in [",", ".", ";", ":", "?", "!", "-", "_", "/", "\\", "(", ")", "[", "]"]:
        clean_text_raw = clean_text_raw.replace(ch, " ")

    raw_words = [w.strip() for w in clean_text_raw.split() if len(w.strip()) >= 3]

    for row in search_rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        ten_raw = str(ten or "").lower().strip()
        ten_norm = normalize_text(ten)
        base_norm = _agency_base_name(ten)

        if not ten_norm:
            continue

        score = 0

        if ten_raw and ten_raw in text_raw:
            score += 20000

        ten_raw_words = [w.strip() for w in ten_raw.split() if len(w.strip()) >= 3]

        # Nếu người dân đang hỏi CSKV theo địa bàn/TDP thì không chấm điểm tên cán bộ theo từng từ rời.
        # Tránh lỗi "Hoàng Quốc Việt" khớp sai với tên cán bộ có chữ "Hoàng" hoặc "Việt".
        if normalize_text(bo_phan) != "cskv":
            for w in ten_raw_words:
                if w in raw_words:
                    score += 12000

        if score == 0:
            if ten_norm in text_norm:
                score += 8000

            if base_norm and base_norm in text_norm:
                score += 7000

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            name_results.append(row)

    if name_results:
        name_results.sort(key=lambda r: (-r["_SCORE"], r["_UU_TIEN"]))

        best_score = name_results[0].get("_SCORE", 0)

        if best_score >= 20000:
            return name_results[:1]

        same_score_results = [
            row for row in name_results
            if row.get("_SCORE", 0) == best_score
        ]

        return same_score_results[:limit]

    keyword_results = []

    for row in search_rows:
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        tdp = get_first(row, "TDP")
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        chuc_nang = get_first(row, "CHUC_NANG", "CHỨC_NĂNG")
        row_bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")

        score = 0

        tdp_norm = normalize_text(tdp)
        tu_khoa_norm = normalize_text(tu_khoa)

        exact_area_score = 0
        for area in split_keywords(tdp):
            area_norm = normalize_text(area)
            if area_norm and area_norm in text_norm:
                exact_area_score += 50000

        for area in split_keywords(tu_khoa):
            area_norm = normalize_text(area)
            if area_norm and area_norm in text_norm:
                if any(ch.isdigit() for ch in area_norm):
                    exact_area_score += 30000
                elif len(area_norm.split()) >= 2:
                    exact_area_score += 25000

        score += exact_area_score

        if exact_area_score > 0:
            score += keyword_score(user_text, tu_khoa, 8)
            score += phrase_score(user_text, tdp, 6)
        else:
            score += keyword_score(user_text, tu_khoa, 4)

        score += phrase_score(user_text, ten, 1)
        score += phrase_score(user_text, chuc_nang, 1)

        if row_bo_phan:
            score += phrase_score(user_text, row_bo_phan, 3)
        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            keyword_results.append(row)

    if keyword_results:
        keyword_results.sort(key=lambda r: (-r["_SCORE"], r["_UU_TIEN"]))

        if bo_phan and normalize_text(bo_phan) == "cskv":
            return keyword_results[:1]

        best_score = keyword_results[0].get("_SCORE", 0)
        second_score = keyword_results[1].get("_SCORE", 0) if len(keyword_results) > 1 else 0

        if len(keyword_results) == 1:
            return keyword_results[:1]

        if best_score >= second_score + 10:
            return keyword_results[:1]

        return keyword_results[:limit]
    if bo_phan:
        results = []
        for row in search_rows:
            row["_SCORE"] = 10000
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            results.append(row)

        results.sort(
            key=lambda r: (
                r["_UU_TIEN"],
                get_first(r, "TEN_CO_QUAN", "HỌ_TÊN", "HO_TEN")
            )
        )
        return results[:limit]

    fallback_results = []

    for row in active_rows:
        score = 0
        score += phrase_score(user_text, get_first(row, "CHUC_NANG", "CHỨC_NĂNG"), 3)
        score += phrase_score(user_text, get_first(row, "GHI_CHU", "GHI_CHÚ"), 1)
        score += phrase_score(user_text, get_first(row, "BO_PHAN", "BỘ_PHẬN"), 1)
        score += phrase_score(user_text, get_first(row, "TDP"), 1)

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(
                get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999)
            )
            fallback_results.append(row)

    fallback_results.sort(key=lambda r: (-r["_SCORE"], r["_UU_TIEN"]))
    return fallback_results[:limit]

# Chức năng: Tìm câu hỏi thường gặp phù hợp trong sheet FAQ.
# Vai trò: Tra cứu FAQ từ Google Sheets để BOT trả lời các câu hỏi phổ biến.
def search_faq(user_text, limit=3):
    results = []

    for row in read_faq():
        score = 0
        score += keyword_score(user_text, get_first(row, "TU_KHOA", "TỪ_KHÓA"), 5)
        score += phrase_score(user_text, get_first(row, "CAU_HOI", "CÂU_HỎI"), 4)
        score += phrase_score(
            user_text,
            get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRA_LOI_DAY_DU"),
            1
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            results.append(row)

    results.sort(key=lambda r: (r["_UU_TIEN"], -r["_SCORE"]))
    return results[:limit]

# Chức năng: Tìm thủ tục hành chính phù hợp trong các sheet THU_TUC_*.
# Vai trò: Tra cứu nội dung nghiệp vụ thủ tục từ Google Sheets.
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


# Chức năng: Liệt kê các thủ tục trong một sheet THU_TUC_*.
# Đầu vào: sheet - tên sheet; limit - số thủ tục tối đa.
# Đầu ra: Danh sách thủ tục thuộc sheet.
# Vai trò: Hiển thị danh sách thủ tục theo lĩnh vực để người dân chọn.
def list_procedures_by_sheet(sheet, limit=10):
    rows = []

    for row in read_all_thu_tuc():
        if row.get("_SHEET") == sheet:
            row["_UU_TIEN"] = safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", default=999))
            rows.append(row)

    rows.sort(key=lambda r: r["_UU_TIEN"])
    return rows[:limit]


# Chức năng: Tìm thủ tục theo ID trên toàn bộ các sheet THU_TUC_*.
# Đầu vào: procedure_id - mã thủ tục.
# Đầu ra: Dòng thủ tục hoặc None.
# Vai trò: Phục vụ chọn thủ tục từ danh sách và giữ context thủ tục.
def find_procedure_by_id(procedure_id):
    pid = str(procedure_id or "").strip()
    if not pid:
        return None

    for row in read_all_thu_tuc():
        if str(row.get("ID", "")).strip() == pid:
            return row

    return None


# Chức năng: Định dạng một dòng thông tin liên hệ để trả lời người dân.
# Đầu vào: row - dòng dữ liệu từ TRA_CUU_LIEN_HE.
# Đầu ra: Chuỗi trả lời đã định dạng.
# Vai trò: Chuẩn hóa cách BOT hiển thị thông tin liên hệ, cán bộ, cơ quan, bản đồ.
def format_lien_he(row):
    parts = []
    ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HỌ_TÊN", "HO_TEN")
    chuc = get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHUC_VU", "CHỨC_VỤ")
    bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")
    phone = get_first(row, "SO_DIEN_THOAI", "ĐIỆN_THOẠI", "DIEN_THOAI", "PHONE")
    address = get_first(row, "DIA_CHI", "ĐỊA_CHỈ", "ADDRESS")
    note = get_first(row, "GHI_CHU", "GHI_CHÚ")
    map_link = get_first(row, "GOOGLE_MAP", "MAP")

    if ten:
        parts.append(f"📌 {ten}")
    if chuc:
        parts.append(f"Chức năng: {chuc}")
    if bo_phan:
        parts.append(f"Bộ phận: {bo_phan}")
    if address:
        parts.append(f"Địa chỉ: {address}")
    if phone:
        parts.append(f"Điện thoại: {phone}")
    if note:
        parts.append(f"Ghi chú: {note}")
    if map_link:
        parts.append(f"Bản đồ: {map_link}")

    return "\n".join(parts)


# Chức năng: Định dạng một dòng FAQ để trả lời người dân.
# Đầu vào: row - dòng dữ liệu FAQ.
# Đầu ra: Chuỗi câu hỏi và câu trả lời.
# Vai trò: Chuẩn hóa cách hiển thị câu hỏi thường gặp.
def format_faq(row):
    q = get_first(row, "CAU_HOI", "CÂU_HỎI")
    a = get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")
    return f"❓ {q}\n\n{a}" if q and a else (a or q)


# Chức năng: Rút gọn nội dung trình tự/quy trình khi trả lời thủ tục.
# Đầu vào: value - nội dung cần rút gọn; max_len - độ dài tối đa.
# Đầu ra: Chuỗi đã rút gọn.
# Vai trò: Giúp tin nhắn Zalo không quá dài nhưng vẫn giữ nội dung chính.
def _short_steps(value, max_len=700):
    text = compact(value, max_len)
    if not text:
        return ""

    # Nếu nội dung có nhiều bước, chỉ giữ gọn để tin nhắn không quá dài.
    lower = normalize_text(text)
    if "buoc" in lower:
        return text

    return text


# Chức năng: Định dạng một thủ tục hành chính để trả lời người dân.
# Đầu vào: row - dòng dữ liệu thủ tục từ THU_TUC_*.
# Đầu ra: Chuỗi trả lời gồm đối tượng, hồ sơ, quy trình, link DVC và gợi ý hỏi tiếp.
# Vai trò: Chuẩn hóa mẫu trả lời thủ tục hành chính của BOT CAP.
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


# Chức năng: Định dạng nhiều kết quả tìm kiếm thành một tin nhắn trả lời.
# Đầu vào: results - danh sách dòng dữ liệu; formatter - hàm định dạng; limit - số kết quả tối đa.
# Đầu ra: Chuỗi trả lời đánh số thứ tự.
# Vai trò: Hiển thị danh sách kết quả liên hệ, FAQ hoặc thủ tục gần đúng.
def format_multiple_results(results, formatter, limit=3):
    texts = []

    for i, row in enumerate(results[:limit], start=1):
        val = formatter(row)
        if val:
            texts.append(f"{i}. {val}")

    return "\n\n".join(texts)


# Chức năng: Tìm thông tin liên hệ theo đúng tên cơ quan/cán bộ.
# Đầu vào: name - tên cơ quan hoặc họ tên cần tìm.
# Đầu ra: Dòng liên hệ phù hợp hoặc None.
# Vai trò: Liên kết trường CO_QUAN_THUC_HIEN/NOI_NOP của thủ tục sang TRA_CUU_LIEN_HE.
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
