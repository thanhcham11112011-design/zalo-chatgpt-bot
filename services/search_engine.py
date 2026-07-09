import re
from services.sheet_api import read_menu, read_lien_he, read_faq, read_all_thu_tuc
from services.text_utils import normalize_text, get_first, safe_int, split_keywords, compact
from services.logger import debug_print

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
    # Chức năng: Nhận diện bộ phận liên hệ bằng BO_PHAN, TU_KHOA, TDP trong sheet TRA_CUU_LIEN_HE.
    # Vai trò: Chỉ xác định bộ phận khi có tín hiệu BO_PHAN/TU_KHOA, TDP chỉ là tín hiệu bổ sung.
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
        has_department_signal = False
        has_area_signal = False

        bo_phan_norm = normalize_text(bo_phan)
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        tdp = get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN")

        if bo_phan_norm and _contains_phrase(text_norm, bo_phan_norm):
            score += 10000
            has_department_signal = True

        keyword_point = keyword_score(user_text, tu_khoa, 8)
        if keyword_point > 0:
            score += keyword_point
            has_department_signal = True

        for area in split_keywords(tdp):
            area_norm = normalize_text(area)
            if area_norm and len(area_norm.split()) >= 2 and _contains_phrase(text_norm, area_norm):
                score += 3000
                has_area_signal = True
                break

        if score > 0 and has_department_signal:
            candidates.append((
                score,
                safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", "ƯU_TIÊN"), 999),
                bo_phan,
            ))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: (-item[0], item[1]))
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


def _expand_contact_role_terms(value):
    # Chức năng: Mở rộng cách gọi chức vụ chỉ huy Công an phường.
    # Vai trò: Giúp TRA_CUU_LIEN_HE khớp Trưởng CAP/Trưởng Công an phường bằng dữ liệu sheet.
    text = normalize_text(value)
    if not text:
        return ""

    terms = [text]

    if "truong cong an phuong" in text and "truong cap" not in text:
        terms.append("truong cap")

    if "truong cap" in text and "truong cong an phuong" not in text:
        terms.append("truong cong an phuong")

    if "pho truong cong an phuong" in text and "pho cap" not in text:
        terms.append("pho cap")

    if "pho cap" in text and "pho truong cong an phuong" not in text:
        terms.append("pho truong cong an phuong")

    return " ".join(terms)


def _contact_role_conflict(user_text, role_text):
    # Chức năng: Loại trừ kết quả Phó trưởng khi người dân hỏi rõ Trưởng Công an phường.
    # Vai trò: Hạn chế trả nhầm lãnh đạo trong tra cứu liên hệ.
    user_norm = _expand_contact_role_terms(user_text)
    role_norm = _expand_contact_role_terms(role_text)

    asks_chief = ("truong cong an phuong" in user_norm or "truong cap" in user_norm) and "pho" not in user_norm
    role_is_deputy = "pho" in role_norm

    return asks_chief and role_is_deputy


def _contains_phrase(text_norm, phrase_norm):
    # Chức năng: Kiểm tra cụm từ đã chuẩn hóa có xuất hiện nguyên cụm trong câu hỏi.
    # Vai trò: Tránh khớp rộng từng từ rời rạc làm sai kết quả liên hệ.
    if not text_norm or not phrase_norm:
        return False
    return f" {phrase_norm} " in f" {text_norm} " or phrase_norm in text_norm




def _significant_tokens(value):
    # Chức năng: Tách các từ có ý nghĩa từ một giá trị đã chuẩn hóa.
    # Vai trò: Loại bỏ từ quá ngắn để phân biệt tín hiệu bộ phận với địa bàn.
    return set(x for x in normalize_text(value).split() if len(x) >= 3)




CONTACT_GENERIC_WORDS = {
    "so", "dien", "thoai", "sdt", "lien", "he", "gap", "dong", "chi",
    "cua", "toi", "muon", "can", "xin", "cho", "hoi", "biet", "to", "tdp",
    "dan", "pho", "phu", "trach", "can", "bo", "ong", "ba", "anh", "chị", "chi",
}


def _department_alias_tokens(row):
    # Chức năng: Lấy các token nhận diện bộ phận từ BO_PHAN và TU_KHOA của dòng liên hệ.
    # Vai trò: Cho phép nhận đúng ANTT/ANCS/CSKV theo dữ liệu sheet, không khớp theo địa bàn trần.
    alias_tokens = set()

    bo_phan_tokens = {
        token for token in _significant_tokens(get_first(row, "BO_PHAN", "BỘ_PHẬN"))
        if token not in CONTACT_GENERIC_WORDS
    }
    alias_tokens.update(bo_phan_tokens)

    area_tokens = _significant_tokens(get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN"))
    name_tokens = _significant_tokens(get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN"))

    for kw in split_keywords(get_first(row, "TU_KHOA", "TỪ_KHÓA")):
        kw_tokens = _significant_tokens(kw)
        if not kw_tokens:
            continue

        has_area = bool(area_tokens and kw_tokens.intersection(area_tokens))
        if not has_area:
            continue

        for token in kw_tokens:
            if token in area_tokens:
                continue
            if token in name_tokens:
                continue
            if token in CONTACT_GENERIC_WORDS:
                continue
            alias_tokens.add(token)

    return alias_tokens


def _department_token_signal(user_text, row):
    # Chức năng: Kiểm tra câu hỏi có nêu token nhận diện bộ phận theo dữ liệu sheet hay không.
    # Vai trò: Bắt đúng các cách viết như ANTT/ANCS/CSKV dù người dân đảo thứ tự từ trong câu hỏi.
    text_tokens = set(x for x in normalize_text(user_text).split() if len(x) >= 3)
    if not text_tokens:
        return False

    alias_tokens = _department_alias_tokens(row)
    return bool(alias_tokens and text_tokens.intersection(alias_tokens))


def _requires_person_name_match(user_text):
    # Chức năng: Nhận diện câu hỏi đang yêu cầu số điện thoại của một đồng chí cụ thể.
    # Vai trò: Không để từ khóa chung như “số điện thoại” kéo nhầm danh sách chỉ huy hoặc bộ phận khác.
    text_norm = normalize_text(user_text)
    if not text_norm:
        return False

    person_markers = ["dong chi", "dc", "can bo"]
    if not any(marker in text_norm for marker in person_markers):
        return False

    tokens = [x for x in text_norm.split() if len(x) >= 3 and x not in CONTACT_GENERIC_WORDS]
    return len(tokens) >= 2

def _keyword_has_non_area_signal(user_text, row):
    # Chức năng: Kiểm tra từ khóa khớp có chứa tín hiệu ngoài tên địa bàn/TDP.
    # Vai trò: Không để từ khóa địa bàn trần làm lẫn CSKV với ANTTCS/ANCS.
    text_norm = normalize_text(user_text)
    if not text_norm:
        return False

    if _department_token_signal(user_text, row):
        return True

    area_tokens = _significant_tokens(get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN"))

    for kw in split_keywords(get_first(row, "TU_KHOA", "TỪ_KHÓA")):
        kw_norm = normalize_text(kw)
        if not kw_norm or not _contains_phrase(text_norm, kw_norm):
            continue

        kw_tokens = _significant_tokens(kw_norm)
        if any(token not in area_tokens for token in kw_tokens):
            return True

    return False

def _department_keyword_signal(user_text, rows):
    # Chức năng: Kiểm tra câu hỏi có nêu rõ nhóm liên hệ bằng dữ liệu BO_PHAN/TU_KHOA hay không.
    # Vai trò: Chặn khớp địa bàn trần làm lẫn CSKV với ANTTCS/ANCS khi người dân chưa nêu nhóm cần gặp.
    text_norm = normalize_text(user_text)
    if not text_norm:
        return False

    for row in rows:
        bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")

        bo_phan_norm = normalize_text(bo_phan)
        if bo_phan_norm and _contains_phrase(text_norm, bo_phan_norm):
            return True

        if _department_token_signal(user_text, row):
            return True

        if _keyword_has_non_area_signal(user_text, row):
            return True

    return False


def _specific_area_signal(user_text, rows):
    # Chức năng: Kiểm tra câu hỏi có nêu rõ địa bàn/TDP kèm nhóm liên hệ trong TRA_CUU_LIEN_HE hay không.
    # Vai trò: Chỉ cho phép tra cứu theo địa bàn khi người dân nêu rõ nhóm cần gặp để tránh lẫn CSKV với ANTTCS/ANCS.
    text_norm = normalize_text(user_text)
    if not _department_keyword_signal(user_text, rows):
        return False

    for row in rows:
        tdp = get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN")
        for area in split_keywords(tdp):
            area_norm = normalize_text(area)
            if area_norm and len(area_norm.split()) >= 2 and _contains_phrase(text_norm, area_norm):
                return True
    return False


def _specific_name_signal(user_text, rows):
    # Chức năng: Kiểm tra câu hỏi có nêu rõ họ tên cán bộ/cơ quan trong TRA_CUU_LIEN_HE hay không.
    # Vai trò: Tránh khớp nhầm khi người dân chỉ nhập một từ trùng tên riêng.
    text_norm = normalize_text(user_text)
    raw_words = set(x for x in text_norm.split() if len(x) >= 3)

    for row in rows:
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        ten_norm = normalize_text(ten)
        base_norm = _agency_base_name(ten)

        if ten_norm and _contains_phrase(text_norm, ten_norm):
            return True
        if base_norm and len(base_norm.split()) >= 2 and _contains_phrase(text_norm, base_norm):
            return True

        name_tokens = [x for x in ten_norm.split() if len(x) >= 3]
        if len([x for x in name_tokens if x in raw_words]) >= 2:
            return True

    return False


def _specific_role_signal(user_text, rows):
    # Chức năng: Kiểm tra câu hỏi có nêu rõ chức năng/chức vụ đủ cụ thể trong TRA_CUU_LIEN_HE hay không.
    # Vai trò: Cho phép hỏi theo chức vụ nhưng không coi bộ phận chung là kết quả đủ rõ.
    text_norm = normalize_text(user_text)
    matched = []

    for row in rows:
        role_text = get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHUC_VU", "CHỨC_VỤ")
        role_norm = _expand_contact_role_terms(role_text)
        bo_phan_norm = normalize_text(get_first(row, "BO_PHAN", "BỘ_PHẬN"))
        if not role_norm:
            continue

        role_tokens = [x for x in role_norm.split() if len(x) >= 3]
        for size in range(min(5, len(role_tokens)), 1, -1):
            for start in range(0, len(role_tokens) - size + 1):
                phrase = " ".join(role_tokens[start:start + size])
                if phrase == bo_phan_norm:
                    continue
                if _contains_phrase(text_norm, phrase):
                    matched.append(row)
                    break
            else:
                continue
            break

    return bool(matched)


def _specific_unique_keyword_signal(user_text, rows):
    # Chức năng: Kiểm tra từ khóa liên hệ có xác định được một dòng duy nhất hay không.
    # Vai trò: Cho phép từ khóa rõ ràng trong sheet, chặn từ khóa nhóm chung trả danh sách rộng.
    text_norm = normalize_text(user_text)
    matched_ids = set()

    for row in rows:
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        bo_phan_norm = normalize_text(get_first(row, "BO_PHAN", "BỘ_PHẬN"))
        row_id = get_first(row, "ID", "MA", "MÃ", "HO_TEN", "HỌ_TÊN")

        if _department_token_signal(user_text, row) or _keyword_has_non_area_signal(user_text, row):
            matched_ids.add(row_id or id(row))

    return len(matched_ids) == 1


def _has_specific_contact_signal(user_text, rows):
    # Chức năng: Kiểm tra câu hỏi liên hệ đã đủ rõ để trả dữ liệu cá nhân/bộ phận hay chưa.
    # Vai trò: Câu hỏi chỉ nêu bộ phận chung sẽ trả hướng dẫn làm rõ thay vì danh sách rộng.
    phone_digits = re.sub(r"\D+", "", str(user_text or ""))
    if len(phone_digits) >= 9:
        return True

    return (
        _specific_area_signal(user_text, rows)
        or _specific_name_signal(user_text, rows)
        or _specific_role_signal(user_text, rows)
        or _specific_unique_keyword_signal(user_text, rows)
    )

def search_lien_he(user_text, limit=3):
    # Chức năng: Tìm thông tin liên hệ theo pipeline nhận diện BO_PHAN từ TU_KHOA rồi mới chấm điểm.
    # Vai trò: Không để địa bàn/TDP kéo nhầm sang bộ phận khác, không ảnh hưởng FAQ và thủ tục.
    rows = read_lien_he()
    text_norm = normalize_text(user_text)
    text_raw = str(user_text or "").lower()

    if not text_norm:
        return []

    phone_digits = re.sub(r"\D+", "", str(user_text or ""))
    active_rows = []

    for row in rows:
        if not _active_status(row):
            continue

        if not any([
            get_first(row, "BO_PHAN", "BỘ_PHẬN"),
            get_first(row, "TU_KHOA", "TỪ_KHÓA"),
            get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN"),
            get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHUC_VU", "CHỨC_VỤ"),
            get_first(row, "SO_DIEN_THOAI", "ĐIỆN_THOẠI", "DIEN_THOAI", "PHONE"),
        ]):
            continue

        active_rows.append(row)

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

        phone_results.sort(key=lambda r: (-safe_int(r.get("_SCORE", 0)), safe_int(r.get("_UU_TIEN", 999))))
        return phone_results[:1]

    text_tokens = set(x for x in text_norm.split() if len(x) >= 3 and x not in CONTACT_GENERIC_WORDS)
    dept_candidates = {}

    for row in active_rows:
        bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")
        bo_phan_norm = normalize_text(bo_phan)

        if not bo_phan_norm:
            continue

        row_score = 0
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        ten_norm = normalize_text(get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN"))
        base_norm = _agency_base_name(get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN"))

        if ten_norm and len(ten_norm.split()) >= 2 and _contains_phrase(text_norm, ten_norm):
            row_score += 60000

        if base_norm and len(base_norm.split()) >= 2 and _contains_phrase(text_norm, base_norm):
            row_score += 55000

        if _contains_phrase(text_norm, bo_phan_norm):
            row_score += 15000

        if _department_token_signal(user_text, row):
            row_score += 30000


        for kw in split_keywords(tu_khoa):
            kw_norm = normalize_text(kw)
            if not kw_norm:
                continue

            kw_phrase_match = (f" {kw_norm} " in f" {text_norm} ") or (len(kw_norm.split()) > 1 and kw_norm in text_norm)
            if kw_phrase_match and not (len(kw_norm.split()) == 1 and len(kw_norm) <= 2):
                area_tokens = _significant_tokens(get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN"))
                name_tokens = _significant_tokens(get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN"))
                kw_tokens = set(x for x in kw_norm.split() if len(x) >= 3 and x not in CONTACT_GENERIC_WORDS)
                non_area_tokens = kw_tokens - area_tokens - name_tokens

                if non_area_tokens or not area_tokens:
                    row_score += 40000 + min(len(kw_norm), 120)

        if row_score <= 0:
            continue

        current = dept_candidates.get(bo_phan_norm)
        priority = safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", "ƯU_TIÊN"), 999)
        if not current or row_score > current[0] or (row_score == current[0] and priority < current[1]):
            dept_candidates[bo_phan_norm] = (row_score, priority, bo_phan)

    bo_phan = ""
    if dept_candidates:
        sorted_depts = sorted(dept_candidates.values(), key=lambda item: (-item[0], item[1], normalize_text(item[2])))
        best_score = sorted_depts[0][0]
        second_score = sorted_depts[1][0] if len(sorted_depts) > 1 else 0
        if best_score >= 10000 and best_score >= second_score + 500:
            bo_phan = sorted_depts[0][2]

    bo_phan_norm = normalize_text(bo_phan)
    search_rows = active_rows

    if bo_phan_norm:
        search_rows = [
            row for row in active_rows
            if normalize_text(get_first(row, "BO_PHAN", "BỘ_PHẬN")) == bo_phan_norm
        ]

    has_area_signal = False
    has_name_signal = False

    for row in search_rows:
        tdp = get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN")
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        ten_norm = normalize_text(ten)
        ten_tokens = [x for x in ten_norm.split() if len(x) >= 3]

        for area in split_keywords(tdp):
            area_norm = normalize_text(area)
            if area_norm and len(area_norm.split()) >= 2 and _contains_phrase(text_norm, area_norm):
                has_area_signal = True

        if ten_norm and _contains_phrase(text_norm, ten_norm):
            has_name_signal = True
        elif ten_tokens and len([x for x in ten_tokens if x in text_tokens]) >= 2:
            has_name_signal = True

    has_many_tdp_rows = bo_phan_norm and len(search_rows) > limit and any(
        get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN") for row in search_rows
    )

    if has_many_tdp_rows and not has_area_signal and not has_name_signal:
        debug_print(
            "CONTACT",
            f"QUESTION: {user_text}",
            f"BO_PHAN={bo_phan}",
            "NEED_AREA_OR_NAME_FOR_TDP_GROUP",
        )
        return []

    results = []
    asks_deputy = "pho" in text_norm and ("truong" in text_norm or "cap" in text_norm or "cong an phuong" in text_norm)
    asks_chief = ("truong cap" in text_norm or "truong cong an phuong" in text_norm) and "pho" not in text_norm

    for row in search_rows:
        score = 0
        notes = []
        ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN")
        tdp = get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN")
        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        chuc_nang = get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHUC_VU", "CHỨC_VỤ")
        ten_norm = normalize_text(ten)
        ten_raw = str(ten or "").lower().strip()
        base_norm = _agency_base_name(ten)
        chuc_nang_norm = _expand_contact_role_terms(chuc_nang)
        row_bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")

        if _contact_role_conflict(user_text, chuc_nang):
            continue

        if asks_deputy and "pho" not in chuc_nang_norm:
            continue

        if asks_chief and "pho" in chuc_nang_norm:
            continue

        if ten_raw and ten_raw in text_raw:
            score += 120000
            notes.append("FULL_NAME_RAW")

        if ten_norm and _contains_phrase(text_norm, ten_norm):
            score += 110000
            notes.append("FULL_NAME")

        if base_norm and len(base_norm.split()) >= 2 and _contains_phrase(text_norm, base_norm):
            score += 90000
            notes.append("BASE_NAME")

        ten_tokens = [x for x in ten_norm.split() if len(x) >= 3]
        matched_name_tokens = [x for x in ten_tokens if x in text_tokens]
        if len(matched_name_tokens) >= 2:
            score += 70000 + len(matched_name_tokens) * 5000
            notes.append("NAME_TOKEN")

        if bo_phan_norm:
            for area in split_keywords(tdp):
                area_norm = normalize_text(area)
                if area_norm and len(area_norm.split()) >= 2 and _contains_phrase(text_norm, area_norm):
                    score += 35000
                    notes.append("AREA")
                    break

        role_score = 0
        role_tokens = []
        matched_role_tokens = []

        if bo_phan_norm or has_name_signal:
            role_score = phrase_score(
                _expand_contact_role_terms(user_text),
                chuc_nang_norm,
                10,
            )

            role_tokens = [
                x for x in chuc_nang_norm.split()
                if len(x) >= 3 and x != normalize_text(row_bo_phan)
            ]
            matched_role_tokens = [x for x in role_tokens if x in text_tokens]

            role_words = [x for x in chuc_nang_norm.split() if len(x) >= 2]
            role_phrase_bonus = 0
            for size in range(min(4, len(role_words)), 1, -1):
                for start in range(0, len(role_words) - size + 1):
                    phrase = " ".join(role_words[start:start + size])
                    if phrase == normalize_text(row_bo_phan):
                        continue
                    if f" {phrase} " in f" {text_norm} " or phrase in text_norm:
                        role_phrase_bonus = 25000 + size * 1000
                        break
                if role_phrase_bonus:
                    break

            if role_score > 0:
                score += 10000 + role_score
                notes.append("ROLE")

            if matched_role_tokens:
                score += len(set(matched_role_tokens)) * 12000
                notes.append("ROLE_TOKEN")

            if role_phrase_bonus:
                score += role_phrase_bonus
                notes.append("ROLE_PHRASE")

        keyword_exact = 0
        keyword_token = 0
        for kw in split_keywords(tu_khoa):
            kw_norm = normalize_text(kw)
            if not kw_norm:
                continue

            kw_phrase_match = (f" {kw_norm} " in f" {text_norm} ") or (len(kw_norm.split()) > 1 and kw_norm in text_norm)
            if kw_phrase_match and not (len(kw_norm.split()) == 1 and len(kw_norm) <= 2):
                area_tokens = _significant_tokens(tdp)
                name_tokens = _significant_tokens(ten)
                kw_tokens = set(x for x in kw_norm.split() if len(x) >= 3 and x not in CONTACT_GENERIC_WORDS)
                non_area_tokens = kw_tokens - area_tokens - name_tokens
                if non_area_tokens or not area_tokens:
                    keyword_exact = max(keyword_exact, 30000 + min(len(kw_norm), 120))
                elif bo_phan_norm:
                    keyword_exact = max(keyword_exact, 8000)
            else:
                kw_tokens = set(x for x in kw_norm.split() if len(x) >= 3 and x not in CONTACT_GENERIC_WORDS)
                matched_kw_tokens = kw_tokens.intersection(text_tokens)
                if len(matched_kw_tokens) >= 2:
                    keyword_token = max(keyword_token, len(matched_kw_tokens) * 3000)

        if keyword_exact:
            score += keyword_exact
            notes.append("KEYWORD_EXACT")

        if keyword_token and bo_phan_norm:
            score += keyword_token
            notes.append("KEYWORD_TOKEN")

        if bo_phan_norm:
            score += 5000
            notes.append("BO_PHAN_FILTER")
        else:
            score += phrase_score(user_text, row_bo_phan, 3)

        if score <= 0:
            continue

        results.append(_add_meta(
            row=row,
            route="LIEN_HE",
            score=score,
            sheet="TRA_CUU_LIEN_HE",
            row_id=get_first(row, "ID", "MA", "MÃ"),
            note="|".join(notes),
        ))

    if not results:
        debug_print(
            "CONTACT",
            f"QUESTION: {user_text}",
            f"BO_PHAN={bo_phan or 'NONE'}",
            "NO_MATCH",
        )
        return []

    results.sort(key=lambda r: (-safe_int(r.get("_SCORE", 0)), safe_int(r.get("_UU_TIEN", 999))))
    best_score = safe_int(results[0].get("_SCORE", 0))
    second_score = safe_int(results[1].get("_SCORE", 0)) if len(results) > 1 else 0

    debug_print(
        "CONTACT",
        f"QUESTION: {user_text}",
        f"BO_PHAN={bo_phan or 'AUTO'}",
        *[
            f"{get_first(r,'TEN_CO_QUAN','TÊN_CƠ_QUAN','HO_TEN','HỌ_TÊN')} SCORE={r.get('_SCORE')} NOTE={r.get('_NOTE')}"
            for r in results[:5]
        ]
    )

    if has_name_signal:
        return results[:1]

    if len(results) == 1:
        return results[:1]

    same_score_results = [row for row in results if safe_int(row.get("_SCORE", 0)) == best_score]
    next_distinct_score = 0
    for row in results:
        row_score = safe_int(row.get("_SCORE", 0))
        if row_score != best_score:
            next_distinct_score = row_score
            break

    if next_distinct_score and best_score >= next_distinct_score + 8000:
        return same_score_results[:limit]

    if best_score >= second_score + 8000:
        return results[:1]

    return results[:limit]

def search_faq(user_text, limit=3):
    # Chức năng: Tìm câu hỏi thường gặp phù hợp trong sheet FAQ.
    # Vai trò: Chặn FAQ liên kết thủ tục cướp câu hỏi chi tiết ngắn khi chưa đủ căn cứ.
    results = []
    user_norm = normalize_text(user_text)

    if not user_norm:
        return []

    detail_keys = [
        "ho so", "giay to", "can gi", "gom gi", "le phi", "phi",
        "thoi han", "bao lau", "may ngay", "o dau", "lam o dau",
        "nop o dau", "noi nop", "noi lam", "dia chi", "link",
        "online", "truc tuyen", "ket qua", "nhan ket qua",
    ]
    user_tokens = [x for x in user_norm.split() if x]
    is_short_detail_question = len(user_tokens) <= 5 and any(k in user_norm for k in detail_keys)

    for row in read_faq():
        if not _active_status(row):
            continue

        keywords = get_first(row, "TU_KHOA", "TỪ_KHÓA")
        question = get_first(row, "CAU_HOI", "CÂU_HỎI")
        ways = get_first(row, "CAC_CACH_HOI", "CÁC_CÁCH_HỎI")
        answer = get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")
        related_id = get_first(row, "RELATED_ID", "RELATED", "MA_THU_TUC", "MÃ_THỦ_TỤC")
        ngu_canh = normalize_text(get_first(row, "NGU_CANH", "NGỮ_CẢNH"))

        if is_short_detail_question and related_id and ngu_canh not in ["procedure_context"]:
            continue

        keyword_match = keyword_score(user_text, keywords, 6)
        question_match = phrase_score(user_text, question, 5)
        ways_match = keyword_score(user_text, ways, 5)

        score = keyword_match + question_match + ways_match

        if related_id:
            related_norm = normalize_text(related_id)
            specific_signal = False
            for value in [keywords, question, ways]:
                value_norm = normalize_text(value)
                if not value_norm:
                    continue
                value_tokens = [x for x in value_norm.split() if len(x) >= 3]
                matched_tokens = [x for x in value_tokens if x in user_norm]
                if len(matched_tokens) >= 2 and any(x not in detail_keys for x in matched_tokens):
                    specific_signal = True
                    break
            if related_norm and related_norm in user_norm:
                specific_signal = True
            if not specific_signal and score < 120:
                continue

        if score < 35:
            continue

        if not answer and not related_id:
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

    debug_print(
        "FAQ",
        f"USER_TEXT: {user_text}",
        *[
            f"{get_first(r,'ID')} SCORE={r.get('_SCORE')} PRIORITY={r.get('_UU_TIEN')} QUESTION={get_first(r,'CAU_HOI','CÂU_HỎI')} RELATED={get_first(r,'RELATED_ID')}"
            for r in results[:5]
        ]
    )

    return results[:limit]

def search_thu_tuc(user_text, limit=5, sheet=None):
    # Chức năng: Tìm thủ tục hành chính phù hợp trong các sheet THU_TUC_*.
    # Vai trò: Chấm điểm toàn bộ dữ liệu trước khi sắp xếp, không trả sớm trong vòng lặp.
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
