import re
from services.sheet_api import read_menu, read_lien_he, read_faq, read_all_thu_tuc
from services.text_utils import normalize_text, get_first, safe_int, split_keywords, compact


def _add_meta(row, route="", score=0, sheet="", row_id="", note=""):
    # Chức năng: Gắn metadata tìm kiếm vào một dòng kết quả.
    # Vai trò: Giúp BOT truy vết ROUTE, SCORE, SHEET, ROW_ID khi ghi log và trả lời.
    row["_ROUTE"] = route
    row["_SCORE"] = score
    row["_SHEET"] = sheet or row.get("_SHEET", "")
    row["_ROW_ID"] = row_id or get_first(row, "ID", "MA", "MÃ")
    row["_NOTE"] = note
    row["_UU_TIEN"] = safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", default=999))
    return row


def _sort_results(results):
    # Chức năng: Sắp xếp kết quả theo ưu tiên và điểm khớp.
    # Vai trò: Bảo đảm BOT chọn kết quả tốt nhất, hạn chế trả lời nhầm.
    results.sort(key=lambda r: (safe_int(r.get("_UU_TIEN", 999)), -safe_int(r.get("_SCORE", 0))))
    return results


def _active_status(row):
    # Chức năng: Kiểm tra trạng thái hoạt động của một dòng dữ liệu.
    # Vai trò: Dùng chung cho các hàm tìm kiếm để chỉ xử lý dữ liệu đang bật.
    trang_thai = normalize_text(get_first(row, "TRANG_THAI", "TRẠNG_THÁI", "STATUS", "ACTIVE"))
    return trang_thai not in ["off", "inactive", "false", "0", "no", "khong", "không", "ngung", "ngừng", "dung", "dừng"]


def detect_bo_phan_contact(user_text):
    # Chức năng: Nhận diện bộ phận liên hệ bằng dữ liệu trong sheet TRA_CUU_LIEN_HE.
    # Vai trò: Loại bỏ danh sách bộ phận hardcode, để Google Sheets quyết định nhóm liên hệ.
    text_norm = normalize_text(user_text)

    if not text_norm:
        return ""

    candidates = []

    for row in read_lien_he():
        if not _active_status(row):
            continue

        bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")
        if not bo_phan:
            continue

        score = 0
        score += phrase_score(user_text, bo_phan, 6)
        score += keyword_score(user_text, get_first(row, "TU_KHOA", "TỪ_KHÓA"), 5)
        score += phrase_score(user_text, get_first(row, "CHUC_NANG", "CHỨC_NĂNG"), 2)

        if score > 0:
            candidates.append((score, safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", "ƯU_TIÊN"), 999), bo_phan))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: (item[1], -item[0]))
    return candidates[0][2]

def keyword_score(user_text, keywords, weight=1):
    # Chức năng: Chấm điểm khớp từ khóa giữa câu hỏi và chuỗi từ khóa trong Sheet.
    # Vai trò: Là nền tảng chấm điểm cho MENU, liên hệ, FAQ và thủ tục.
    user_norm = normalize_text(user_text)
    if not user_norm:
        return 0

    user_words = set(user_norm.split())
    score = 0

    for kw in split_keywords(keywords):
        kw_norm = normalize_text(kw)
        if not kw_norm:
            continue

        kw_words = kw_norm.split()

        if kw_norm == user_norm:
            score += 100 * weight
        elif len(kw_words) == 1:
            if len(kw_norm) <= 2:
                continue
            if kw_norm in user_words:
                score += len(kw_norm) * weight
        elif kw_norm in user_norm:
            score += len(kw_norm) * weight

    return score

def field_score(user_text, *fields):
    # Chức năng: Chấm điểm nhiều trường dữ liệu theo cơ chế từ khóa.
    # Vai trò: Hỗ trợ gom điểm từ nhiều cột dữ liệu khi tìm kiếm.
    score = 0
    for field in fields:
        score += keyword_score(user_text, field)
    return score


def phrase_score(user_text, value, weight=1):
    # Chức năng: Chấm điểm khớp cụm từ giữa câu hỏi và một giá trị dữ liệu.
    # Vai trò: Giúp BOT tìm theo tên cơ quan, tên thủ tục, mô tả hoặc chức năng.
    user_norm = normalize_text(user_text)
    value_norm = normalize_text(value)

    if not user_norm or not value_norm:
        return 0

    score = 0

    if user_norm == value_norm:
        score += 100 * weight

    if user_norm in value_norm or value_norm in user_norm:
        score += 30 * weight

    user_tokens = [x for x in user_norm.split() if len(x) >= 2]
    value_tokens = set(x for x in value_norm.split() if len(x) >= 2)

    for token in user_tokens:
        if token in value_tokens:
            score += 3 * weight
        elif token in value_norm:
            score += 1 * weight

    return score


def search_menu(user_text):
    # Chức năng: Tìm chức năng MENU phù hợp với nội dung người dân nhập.
    # Vai trò: Định tuyến nhóm chức năng chính của BOT trước khi tìm dữ liệu chi tiết.
    user_norm = normalize_text(user_text)
    results = []

    for row in read_menu():
        menu_id = str(row.get("ID", "")).strip()
        title = get_first(row, "TEN_CHUC_NANG", "TÊN_CHỨC_NĂNG", "TEN", "CHU_DE", "MO_TA", "MÔ_TẢ")
        keywords = get_first(row, "TU_KHOA", "TỪ_KHÓA", "TU KHOA")
        desc = get_first(row, "MO_TA", "MÔ_TẢ")
        sheet = get_first(row, "SHEET_DU_LIEU", "SHEET", "SHEET_DATA")

        score = 0

        if user_norm and user_norm == normalize_text(menu_id):
            score += 1000

        score += keyword_score(user_text, keywords, 5)
        score += phrase_score(user_text, title, 3)
        score += phrase_score(user_text, desc, 1)

        if score > 0:
            results.append(_add_meta(
                row=row,
                route="MENU",
                score=score,
                sheet=sheet or "MENU",
                row_id=menu_id,
                note="MENU_MATCH",
            ))

    _sort_results(results)
    return results[0] if results else None


def _agency_base_name(name):
    # Chức năng: Chuẩn hóa tên cơ quan về tên gốc để so khớp rộng.
    # Vai trò: Giúp BOT nhận diện tên cơ quan khi người dân nhập thiếu phần mô tả.
    text = normalize_text(name)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\bco so\s*\d+\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _keyword_exact_match(user_text, keywords):
    # Chức năng: Kiểm tra câu hỏi có khớp rõ một từ khóa trong cột TU_KHOA hay không.
    # Vai trò: Là tầng lọc chính xác trước khi tìm kiếm rộng.
    user_norm = normalize_text(user_text)

    for kw in split_keywords(keywords):
        kw_norm = normalize_text(kw)
        if kw_norm and kw_norm in user_norm:
            return True

    return False

def search_lien_he(user_text, limit=3):
    # Chức năng: Tìm thông tin liên hệ trong sheet TRA_CUU_LIEN_HE.
    # Vai trò: Tra cứu cán bộ, bộ phận, cơ quan, trực ban, địa chỉ, số điện thoại từ Google Sheets.
    rows = read_lien_he()
    text_raw = str(user_text or "").lower()
    text_norm = normalize_text(user_text)

    if not text_norm:
        return []

    print("===== DEBUG CONTACT =====")
    print("CONTACT_QUERY:", user_text)
    print("TEXT_NORM:", text_norm)
    print("=========================")

    phone_digits = re.sub(r"\D+", "", str(user_text or ""))

    active_rows = [row for row in rows if _active_status(row)]

    if len(phone_digits) >= 9:
        phone_results = []

        for row in active_rows:
            phone = get_first(row, "SO_DIEN_THOAI", "ĐIỆN_THOẠI", "DIEN_THOAI", "PHONE")
            phone_norm = re.sub(r"\D+", "", str(phone or ""))

            if phone_norm and phone_digits in phone_norm:
                phone_results.append(_add_meta(
                    row=row,
                    route="LIEN_HE",
                    score=100000,
                    sheet="TRA_CUU_LIEN_HE",
                    row_id=get_first(row, "ID", "MA", "MÃ"),
                    note="PHONE_MATCH",
                ))

        if phone_results:
            _sort_results(phone_results)
            return phone_results[:1]

        return []

    bo_phan = detect_bo_phan_contact(user_text)
    bo_phan_norm = normalize_text(bo_phan)

    search_rows = active_rows

    if bo_phan:
        search_rows = []
        for row in active_rows:
            row_bo_phan_norm = normalize_text(get_first(row, "BO_PHAN", "BỘ_PHẬN"))
            row_chuc_nang_norm = normalize_text(get_first(row, "CHUC_NANG", "CHỨC_NĂNG"))
            row_tu_khoa_norm = normalize_text(get_first(row, "TU_KHOA", "TỪ_KHÓA"))

            if row_bo_phan_norm == bo_phan_norm:
                search_rows.append(row)
            elif bo_phan_norm and (bo_phan_norm in row_chuc_nang_norm or bo_phan_norm in row_tu_khoa_norm):
                search_rows.append(row)

    clean_text_raw = text_raw
    for ch in [",", ".", ";", ":", "?", "!", "-", "_", "/", "\\", "(", ")", "[", "]"]:
        clean_text_raw = clean_text_raw.replace(ch, " ")

    raw_words = [w.strip() for w in clean_text_raw.split() if len(w.strip()) >= 3]

    area_results = []

    for row in search_rows:
        tdp = get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN")
        score = 0

        for area in split_keywords(tdp):
            area_norm = normalize_text(area)
            if area_norm and area_norm in text_norm:
                score += 50000

        if score > 0:
            area_results.append(_add_meta(
                row=row,
                route="LIEN_HE",
                score=score,
                sheet="TRA_CUU_LIEN_HE",
                row_id=get_first(row, "ID", "MA", "MÃ"),
                note="AREA_MATCH",
            ))

    if area_results:
        _sort_results(area_results)

        best_score = area_results[0].get("_SCORE", 0)
        same_score_results = [row for row in area_results if row.get("_SCORE", 0) == best_score]
        return same_score_results[:limit]

    full_name_results = []

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

        if ten_norm and ten_norm in text_norm:
            score += 18000

        if base_norm and base_norm in text_norm:
            score += 15000

        if score > 0:
            full_name_results.append(_add_meta(
                row=row,
                route="LIEN_HE",
                score=score,
                sheet="TRA_CUU_LIEN_HE",
                row_id=get_first(row, "ID", "MA", "MÃ"),
                note="FULL_NAME_MATCH",
            ))

    if full_name_results:
        keyword_rows = []

        for row in search_rows:
            tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")
            keyword_match = keyword_score(user_text, tu_khoa, 6)

            if keyword_match > 0:
                keyword_rows.append(_add_meta(
                    row=row,
                    route="LIEN_HE",
                    score=keyword_match,
                    sheet="TRA_CUU_LIEN_HE",
                    row_id=get_first(row, "ID", "MA", "MÃ"),
                    note="KEYWORD_BEFORE_FULL_NAME",
                ))

        if keyword_rows:
            keyword_rows.sort(key=lambda r: (safe_int(r.get("_UU_TIEN", 999)), -safe_int(r.get("_SCORE", 0))))
            return keyword_rows[:1]

        _sort_results(full_name_results)
        return full_name_results[:1]

    name_results = []

    for row in search_rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        ten_raw = str(ten or "").lower().strip()

        if not ten_raw:
            continue

        ten_raw_words = [w.strip() for w in ten_raw.split() if len(w.strip()) >= 3]
        score = 0
        matched_tokens = 0

        for w in ten_raw_words:
            if w in raw_words:
                matched_tokens += 1
                score += 12000

        if matched_tokens < 2:
            continue

        if score > 0:
            name_results.append(_add_meta(
                row=row,
                route="LIEN_HE",
                score=score,
                sheet="TRA_CUU_LIEN_HE",
                row_id=get_first(row, "ID", "MA", "MÃ"),
                note="NAME_TOKEN_MATCH",
            ))

    if name_results:
        _sort_results(name_results)

        best_score = name_results[0].get("_SCORE", 0)
        same_score_results = [row for row in name_results if row.get("_SCORE", 0) == best_score]

        if len(same_score_results) == 1:
            return same_score_results[:1]

        return same_score_results[:limit]

    keyword_results = []

    for row in search_rows:
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        tdp = get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN")
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        chuc_nang = get_first(row, "CHUC_NANG", "CHỨC_NĂNG")
        row_bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")

        keyword_match = keyword_score(user_text, tu_khoa, 4)
        area_match = phrase_score(user_text, tdp, 2)
        name_match = phrase_score(user_text, ten, 1)
        function_match = phrase_score(user_text, chuc_nang, 1)
        department_match = phrase_score(user_text, row_bo_phan, 3) if row_bo_phan else 0

        score = keyword_match + area_match + name_match + function_match + department_match

        if score <= 0:
            continue

        if bo_phan and score > 0:
            score += 500

        keyword_results.append(_add_meta(
            row=row,
            route="LIEN_HE",
            score=score,
            sheet="TRA_CUU_LIEN_HE",
            row_id=get_first(row, "ID", "MA", "MÃ"),
            note="KEYWORD_MATCH",
        ))
    if keyword_results:
        _sort_results(keyword_results)

        keyword_results.sort(
            key=lambda r: (
                safe_int(get_first(r, "UU_TIEN", "ƯU_TIÊN"), default=999),
                -safe_int(r.get("_SCORE", 0)),
            )
        )

        best_score = keyword_results[0].get("_SCORE", 0)
        second_score = keyword_results[1].get("_SCORE", 0) if len(keyword_results) > 1 else 0

        if len(keyword_results) == 1:
            return keyword_results[:1]

        if best_score >= second_score + 10:
            return keyword_results[:1]

        return keyword_results[:limit]

    return []

def search_faq(user_text, limit=3):
    # Chức năng: Tìm câu hỏi thường gặp phù hợp trong sheet FAQ.
    # Vai trò: Tra cứu FAQ từ Google Sheets để BOT trả lời các câu hỏi phổ biến.
    results = []
    user_norm = normalize_text(user_text)

    if not user_norm:
        return []

    for row in read_faq():
        keywords = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        question = get_first(row, "CAU_HOI", "CÂU_HỎI")
        ways = get_first(row, "CAC_CACH_HOI", "CÁC_CÁCH_HỎI")
        answer = get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")

        keyword_match = keyword_score(user_text, keywords, 6)
        question_match = phrase_score(user_text, question, 5)
        ways_match = keyword_score(user_text, ways, 5)

        score = keyword_match + question_match + ways_match

        if score < 35:
            continue

        results.append(_add_meta(
            row=row,
            route="FAQ",
            score=score,
            sheet="FAQ",
            row_id=get_first(row, "ID", "MA", "MÃ"),
            note="FAQ_MATCH",
        ))

    results.sort(
        key=lambda r: (
            -safe_int(r.get("_SCORE", 0)),
            safe_int(r.get("_UU_TIEN", 999)),
        )
    )
    print("===== DEBUG SEARCH FAQ =====")
    print("USER_TEXT:", user_text)
    for r in results[:5]:
        print(
            get_first(r, "ID"),
            "SCORE=", r.get("_SCORE"),
            "UU_TIEN=", r.get("_UU_TIEN"),
            "QUESTION=", get_first(r, "CAU_HOI", "CÂU_HỎI"),
            "RELATED_ID=", get_first(r, "RELATED_ID", "RELATED")
        )
    print("============================")
    return results[:limit]

def search_thu_tuc(user_text, limit=5, sheet=None):
    # Chức năng: Tìm thủ tục hành chính phù hợp trong các sheet THU_TUC_*.
    # Vai trò: Chấm điểm hoàn toàn theo dữ liệu Google Sheets, không dùng từ khóa nghiệp vụ hardcode.
    results = []
    user_norm = normalize_text(user_text)

    if not user_norm:
        return []

    for row in read_all_thu_tuc():
        row_sheet = row.get("_SHEET", "")

        if sheet and row_sheet != sheet:
            continue

        keywords = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
        ma = get_first(row, "ID", "MA", "MÃ")
        mo_ta = get_first(row, "MO_TA", "MÔ_TẢ")
        chu_de = get_first(row, "CHU_DE", "CHỦ_ĐỀ")
        goi_y = get_first(row, "GOI_Y_CAU_HOI", "GỢI_Ý_CÂU_HỎI")
        tra_loi_ngan = get_first(row, "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN")
        noi_nop = get_first(row, "NOI_NOP", "NƠI_NỘP", "CO_QUAN_THUC_HIEN", "CƠ_QUAN_THỰC_HIỆN")

        keyword_match = keyword_score(user_text, keywords, 10)
        title_match = phrase_score(user_text, ten, 8)
        code_match = phrase_score(user_text, ma, 8)
        topic_match = phrase_score(user_text, chu_de, 3)
        desc_match = phrase_score(user_text, mo_ta, 2)
        suggest_match = keyword_score(user_text, goi_y, 4)
        short_answer_match = phrase_score(user_text, tra_loi_ngan, 1)
        place_match = phrase_score(user_text, noi_nop, 1)

        score = (
            keyword_match
            + title_match
            + code_match
            + topic_match
            + desc_match
            + suggest_match
            + short_answer_match
            + place_match
        )

        has_direct_signal = keyword_match > 0 or title_match >= 30 or code_match >= 30 or suggest_match > 0

        if not has_direct_signal:
            continue

        if score < 35:
            continue

        results.append(_add_meta(
            row=row,
            route="THU_TUC",
            score=score,
            sheet=row_sheet,
            row_id=get_first(row, "ID", "MA", "MÃ"),
            note="PROCEDURE_MATCH",
        ))

    _sort_results(results)
    return results[:limit]

def list_procedures_by_sheet(sheet, limit=10):
    # Chức năng: Liệt kê các thủ tục trong một sheet THU_TUC_*.
    # Vai trò: Hiển thị danh sách thủ tục theo lĩnh vực để người dân chọn.
    rows = []

    for row in read_all_thu_tuc():
        if row.get("_SHEET") == sheet:
            rows.append(_add_meta(
                row=row,
                route="THU_TUC_LIST",
                score=0,
                sheet=sheet,
                row_id=get_first(row, "ID", "MA", "MÃ"),
                note="LIST_BY_SHEET",
            ))

    _sort_results(rows)
    return rows[:limit]


def find_procedure_by_id(procedure_id):
    # Chức năng: Tìm thủ tục theo ID trên toàn bộ các sheet THU_TUC_*.
    # Vai trò: Phục vụ chọn thủ tục từ danh sách và giữ context thủ tục.
    pid = str(procedure_id or "").strip()

    if not pid:
        return None

    for row in read_all_thu_tuc():
        row_id = str(get_first(row, "ID", "MA", "MÃ") or "").strip()
        if row_id == pid:
            return _add_meta(
                row=row,
                route="THU_TUC_ID",
                score=100000,
                sheet=row.get("_SHEET", ""),
                row_id=row_id,
                note="ID_MATCH",
            )

    return None

def format_lien_he(row):
    # Chức năng: Định dạng một dòng thông tin liên hệ để trả lời người dân.
    # Vai trò: Chuẩn hóa cách BOT hiển thị thông tin liên hệ, cán bộ, cơ quan, bản đồ.
    parts = []

    ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HỌ_TÊN", "HO_TEN")
    chuc = get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHUC_VU", "CHỨC_VỤ")
    bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")
    tdp = get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN")
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
    if tdp:
        parts.append(f"Địa bàn: {tdp}")
    if address:
        parts.append(f"Địa chỉ: {address}")
    if phone:
        parts.append(f"Điện thoại: {phone}")
    if note:
        parts.append(f"Ghi chú: {note}")
    if map_link:
        parts.append(f"Bản đồ: {map_link}")

    return "\n".join(parts)


def format_faq(row):
    # Chức năng: Định dạng một dòng FAQ để trả lời người dân.
    # Vai trò: Chuẩn hóa cách hiển thị câu hỏi thường gặp.
    q = get_first(row, "CAU_HOI", "CÂU_HỎI")
    a = get_first(
        row,
        "TRA_LOI",
        "TRẢ_LỜI",
        "TRA_LOI_NGAN",
        "TRẢ_LỜI_NGẮN",
        "TRA_LOI_DAY_DU",
        "TRẢ_LỜI_ĐẦY_ĐỦ",
    )

    if q and a:
        return f"❓ {q}\n\n{a}"

    return a or q


def _short_steps(value, max_len=700):
    # Chức năng: Rút gọn nội dung trình tự/quy trình khi trả lời thủ tục.
    # Vai trò: Giúp tin nhắn Zalo không quá dài nhưng vẫn giữ nội dung chính.
    text = compact(value, max_len)

    if not text:
        return ""

    return text


def _append_field(parts, icon, title, value, max_len=700):
    # Chức năng: Bổ sung một trường dữ liệu có định dạng vào nội dung trả lời.
    # Vai trò: Giúp mẫu trả lời thủ tục thống nhất và dễ mở rộng theo cột Google Sheets.
    if value:
        parts.append(f"{icon} {title}:\n{compact(value, max_len)}")

def format_thu_tuc(row):
    # Chức năng: Định dạng thông báo khi BOT xác định được một thủ tục hành chính.
    # Vai trò: Tạo câu trả lời theo cấu hình SETTING_CHAT, không hardcode trường hiển thị.
    from services.sheet_api import read_setting_chat

    field_map = {
        "DOI_TUONG": ("👤", "Đối tượng", ["DOI_TUONG_AP_DUNG", "ĐỐI_TƯỢNG_ÁP_DỤNG"]),
        "DIEU_KIEN": ("✅", "Điều kiện", ["DIEU_KIEN", "ĐIỀU_KIỆN"]),
        "HO_SO": ("📄", "Hồ sơ", ["HO_SO", "HỒ_SƠ"]),
        "TRINH_TU": ("📝", "Trình tự thực hiện", ["TRINH_TU", "TRÌNH_TỰ"]),
        "NOI_NOP": ("📍", "Nơi nộp", ["NOI_NOP", "NƠI_NỘP", "NOI_THUC_HIEN", "NƠI_THỰC_HIỆN"]),
        "THOI_HAN": ("⏱", "Thời hạn", ["THOI_HAN", "THỜI_HẠN"]),
        "LE_PHI": ("💰", "Lệ phí", ["LE_PHI", "LỆ_PHÍ", "PHI"]),
        "KET_QUA": ("✅", "Kết quả", ["KET_QUA", "KẾT_QUẢ"]),
        "CO_SO_PHAP_LY": ("⚖️", "Cơ sở pháp lý", ["CO_SO_PHAP_LY", "CƠ_SỞ_PHÁP_LÝ"]),
        "LINK_DVC": ("🔗", "Link dịch vụ công", ["LINK_DVC", "LINK", "DICH_VU_CONG", "DỊCH_VỤ_CÔNG"]),
        "GOI_Y_CAU_HOI": ("💬", "Có thể hỏi tiếp", ["GOI_Y_CAU_HOI", "GỢI_Ý_CÂU_HỎI"]),
    }

    settings = read_setting_chat() or {}
    display_fields = str(settings.get("THU_TUC_DISPLAY_FIELDS") or "DOI_TUONG,DIEU_KIEN,TRINH_TU").strip()
    selected_fields = [x.strip().upper() for x in display_fields.split(",") if x.strip()]

    ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
    tra_loi_ngan = get_first(row, "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN", "MO_TA", "MÔ_TẢ")

    parts = []

    if ten:
        parts.append(f"📌 {ten}")

    if tra_loi_ngan:
        parts.append(compact(tra_loi_ngan, 900))

    for field in selected_fields:
        config = field_map.get(field)
        if not config:
            continue

        icon, label, keys = config
        value = get_first(row, *keys)

        if not value:
            continue

        if field == "LINK_DVC":
            parts.append(f"{icon} {label}:\n{value}")
        else:
            _append_field(parts, icon, label, value, 900)

    return "\n\n".join([p for p in parts if p])
    
def format_multiple_results(results, formatter, limit=3):
    # Chức năng: Định dạng nhiều kết quả tìm kiếm thành một tin nhắn trả lời.
    # Vai trò: Hiển thị danh sách kết quả liên hệ, FAQ hoặc thủ tục gần đúng.
    texts = []

    for i, row in enumerate(results[:limit], start=1):
        val = formatter(row)
        if val:
            texts.append(f"{i}. {val}")

    return "\n\n".join(texts)

def find_lien_he_by_ten_co_quan(name):
    # Chức năng: Tìm thông tin liên hệ theo đúng tên cơ quan/cán bộ.
    # Vai trò: Liên kết trường CO_QUAN_THUC_HIEN/NOI_NOP của thủ tục sang TRA_CUU_LIEN_HE.
    if not name:
        return None

    name_norm = normalize_text(name)
    rows = read_lien_he()

    for row in rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        if normalize_text(ten) == name_norm:
            return _add_meta(
                row=row,
                route="LIEN_HE",
                score=100000,
                sheet="TRA_CUU_LIEN_HE",
                row_id=get_first(row, "ID", "MA", "MÃ"),
                note="AGENCY_EXACT_MATCH",
            )

    for row in rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        ten_norm = normalize_text(ten)

        if name_norm and ten_norm and (name_norm in ten_norm or ten_norm in name_norm):
            return _add_meta(
                row=row,
                route="LIEN_HE",
                score=50000,
                sheet="TRA_CUU_LIEN_HE",
                row_id=get_first(row, "ID", "MA", "MÃ"),
                note="AGENCY_PARTIAL_MATCH",
            )

    return None
