import re
import unicodedata
from services.sheet_api import read_menu, read_lien_he, read_faq, read_all_thu_tuc, read_filter_bad_word
from services.text_utils import normalize_text, get_first, safe_int, split_keywords, split_list, compact
from services.logger import debug_print



# Chức năng: Chuẩn hóa chuỗi thành các từ nhưng giữ nguyên dấu tiếng Việt.
# Vai trò: Phục vụ so khớp từng từ mà không làm mất sự khác biệt giữa tao, tảo, táo, tạo.
def _tokenize_keep_accents(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.split() if text else []


# Chức năng: Kiểm tra một từ có dấu tiếng Việt hay không.
# Vai trò: Quyết định khi nào được phép so khớp theo dạng bỏ dấu.
def _has_vietnamese_diacritic(value):
    text = str(value or "").lower()

    if "đ" in text:
        return True

    decomposed = unicodedata.normalize("NFD", text)
    return any(unicodedata.category(ch) == "Mn" for ch in decomposed)


# Chức năng: Kiểm tra hai từ có tương đương trong bộ lọc ngôn từ hay không.
# Vai trò: Cho phép bỏ dấu đúng trường hợp nhưng không để tao khớp nhầm tảo, táo hoặc tạo.
def _bad_word_token_match(user_token, pattern_token):
    user_original = str(user_token or "").lower()
    pattern_original = str(pattern_token or "").lower()

    if user_original == pattern_original:
        return True

    user_norm = normalize_text(user_original)
    pattern_norm = normalize_text(pattern_original)

    if not user_norm or user_norm != pattern_norm:
        return False

    if _has_vietnamese_diacritic(pattern_original):
        return True

    return not _has_vietnamese_diacritic(user_original)


# Chức năng: Kiểm tra một mẫu từ ngữ vi phạm có khớp trọn từ hoặc trọn cụm trong câu hỏi hay không.
# Vai trò: So khớp từng từ để tránh nhầm lẫn giữa các từ khác nghĩa sau khi bỏ dấu.
def _bad_word_pattern_match(user_text, pattern, match_type="CUM_TU"):
    user_tokens = _tokenize_keep_accents(user_text)
    pattern_tokens = _tokenize_keep_accents(pattern)

    if not user_tokens or not pattern_tokens:
        return False

    match_type_norm = normalize_text(match_type)

    if match_type_norm in ["chinh xac", "exact"]:
        if len(user_tokens) != len(pattern_tokens):
            return False

        return all(
            _bad_word_token_match(user_token, pattern_token)
            for user_token, pattern_token in zip(user_tokens, pattern_tokens)
        )

    if match_type_norm in ["tu don", "word", "whole word"]:
        if len(pattern_tokens) != 1:
            return False

        return any(
            _bad_word_token_match(user_token, pattern_tokens[0])
            for user_token in user_tokens
        )

    pattern_length = len(pattern_tokens)

    if pattern_length > len(user_tokens):
        return False

    for index in range(len(user_tokens) - pattern_length + 1):
        user_window = user_tokens[index:index + pattern_length]

        matched = all(
            _bad_word_token_match(user_token, pattern_token)
            for user_token, pattern_token in zip(user_window, pattern_tokens)
        )

        if matched:
            return True

    return False

# Chức năng: Tìm quy tắc ngăn chặn từ ngữ thiếu văn hóa trong sheet FILTER_BAD_WORD.
# Vai trò: Chặn sớm nội dung vi phạm bằng dữ liệu Google Sheets trước khi định tuyến nghiệp vụ.
def detect_bad_language(user_text):
    matches = []

    for row in read_filter_bad_word():
        patterns = get_first(
            row,
            "TU_KHOA",
            "TỪ_KHÓA",
            "PATTERN",
            "MAU_CAU",
            "MẪU_CÂU",
        )
        match_type = get_first(
            row,
            "KIEU_KHOP",
            "KIỂU_KHỚP",
            "MATCH_TYPE",
            default="CUM_TU",
        )

        for pattern in split_list(patterns):
            if not _bad_word_pattern_match(user_text, pattern, match_type):
                continue

            item = dict(row)
            item["_MATCHED_PATTERN"] = pattern
            item["_MUC_DO"] = safe_int(
                get_first(row, "MUC_DO", "MỨC_ĐỘ", "LEVEL"),
                1,
            )
            item["_UU_TIEN"] = safe_int(
                get_first(
                    row,
                    "MUC_UU_TIEN",
                    "ƯU_TIÊN",
                    "UU_TIEN",
                ),
                999,
            )
            matches.append(item)
            break

    if not matches:
        return None

    matches.sort(
        key=lambda r: (
            -safe_int(r.get("_MUC_DO", 1)),
            safe_int(r.get("_UU_TIEN", 999)),
        )
    )
    return matches[0]


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
    # Chức năng: Nhận diện bộ phận liên hệ bằng tín hiệu chính xác trong sheet TRA_CUU_LIEN_HE.
    # Vai trò: Chỉ xác định bộ phận khi BO_PHAN hoặc TU_KHOA khớp rõ, tránh cướp luồng FAQ và phản ánh.
    text_norm = normalize_text(user_text)

    if not text_norm:
        return ""

    active_rows = [
        row for row in read_lien_he()
        if _active_status(row)
    ]

    return _detect_contact_department(user_text, active_rows)

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








def _contact_field_values(row):
    # Chức năng: Gom các trường dùng để tra cứu liên hệ từ một dòng TRA_CUU_LIEN_HE.
    # Vai trò: Để Google Sheets quyết định từ khóa, bộ phận, địa bàn, chức năng và họ tên.
    return {
        "bo_phan": get_first(row, "BO_PHAN", "BỘ_PHẬN"),
        "tdp": get_first(row, "TDP", "DIA_BAN", "ĐỊA_BÀN"),
        "keywords": get_first(row, "TU_KHOA", "TỪ_KHÓA"),
        "name": get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HO_TEN", "HỌ_TÊN"),
        "role": get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHUC_VU", "CHỨC_VỤ"),
        "phone": get_first(row, "SO_DIEN_THOAI", "ĐIỆN_THOẠI", "DIEN_THOAI", "PHONE"),
    }


def _exact_keyword_score(user_text, keywords, base_score=0):
    # Chức năng: Chấm điểm khi người dân nhập đúng một từ khóa/cụm từ trong sheet.
    # Vai trò: Ưu tiên dữ liệu TU_KHOA thay vì suy luận nghiệp vụ trong Python.
    user_norm = normalize_text(user_text)
    user_words = set(user_norm.split())
    score = 0

    for kw in split_keywords(keywords):
        kw_norm = normalize_text(kw)
        if not kw_norm:
            continue

        kw_words = [x for x in kw_norm.split() if x]
        if not kw_words:
            continue

        if len(kw_words) == 1:
            if len(kw_norm) >= 3 and kw_norm in user_words:
                score += base_score + 2000 + len(kw_norm) * 5
        elif kw_norm in user_norm:
            score += base_score + 12000 + len(kw_norm) * 10

    return score


def _name_token_score(user_text, name):
    # Chức năng: Chấm điểm khi câu hỏi chứa đúng họ tên hoặc nhiều từ trong họ tên.
    # Vai trò: Ưu tiên khớp nguyên cụm và tránh khớp một phần từ trong TRA_CUU_LIEN_HE.
    user_norm = normalize_text(user_text)
    name_norm = normalize_text(name)

    if not user_norm or not name_norm:
        return 0

    user_box = f" {user_norm} "
    name_box = f" {name_norm} "

    if name_box in user_box:
        return 60000

    user_tokens = set(user_norm.split())
    name_tokens = [x for x in name_norm.split() if len(x) >= 3]
    matched = [x for x in name_tokens if x in user_tokens]

    if name_tokens and len(matched) == len(name_tokens):
        return 45000 + len(matched) * 1000

    if len(matched) >= 2:
        return 35000 + len(matched) * 1000

    return 0



def _detect_contact_department(user_text, rows):
    # Chức năng: Nhận diện bộ phận khi câu hỏi có tín hiệu rõ trong BO_PHAN hoặc TU_KHOA.
    # Vai trò: Phân biệt các dòng cùng địa bàn mà không bắt buộc mọi tra cứu phải có BO_PHAN.
    candidates = {}

    for row in rows:
        fields = _contact_field_values(row)
        department = str(fields.get("bo_phan") or "").strip()
        department_norm = normalize_text(department)
        if not department_norm:
            continue

        score = _exact_keyword_score(user_text, department, 20000)
        area_tokens = set(normalize_text(fields.get("tdp")).split())

        for keyword in split_keywords(fields.get("keywords")):
            keyword_tokens = set(x for x in normalize_text(keyword).split() if len(x) >= 3)
            if keyword_tokens and area_tokens and keyword_tokens.issubset(area_tokens):
                continue
            score += _exact_keyword_score(user_text, keyword, 10000)

        if score <= 0:
            continue

        current = candidates.get(department_norm)
        priority = safe_int(get_first(row, "MUC_UU_TIEN", "UU_TIEN", "ƯU_TIÊN"), 999)
        if not current or score > current[0] or (score == current[0] and priority < current[1]):
            candidates[department_norm] = (score, priority, department)

    if not candidates:
        return ""

    ranked = sorted(candidates.values(), key=lambda item: (-item[0], item[1], normalize_text(item[2])))
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return ""

    return ranked[0][2]

def search_lien_he(user_text, limit=3):
    # Chức năng: Tìm thông tin liên hệ trong sheet TRA_CUU_LIEN_HE.
    # Vai trò: Chấm điểm hoàn toàn theo dữ liệu liên hệ, không hardcode cán bộ/bộ phận.
    text_norm = normalize_text(user_text)
    if not text_norm:
        return []

    active_rows = [row for row in read_lien_he() if _active_status(row)]
    phone_digits = re.sub(r"\D+", "", str(user_text or ""))
    department_filter = _detect_contact_department(user_text, active_rows)
    department_filter_norm = normalize_text(department_filter)

    if len(phone_digits) >= 9:
        phone_results = []
        for row in active_rows:
            fields = _contact_field_values(row)
            phone_norm = re.sub(r"\D+", "", str(fields.get("phone") or ""))
            if phone_norm and phone_digits in phone_norm:
                phone_results.append(_add_meta(
                    row=dict(row),
                    route="LIEN_HE",
                    score=100000,
                    sheet="TRA_CUU_LIEN_HE",
                    row_id=get_first(row, "ID", "MA", "MÃ"),
                    note="PHONE_MATCH",
                ))
        _sort_results(phone_results)
        return phone_results[:1]

    exact_name_results = []
    text_box = f" {text_norm} "

    for row in active_rows:
        fields = _contact_field_values(row)
        name_norm = normalize_text(fields.get("name"))
        name_tokens = [x for x in name_norm.split() if x]

        if len(name_tokens) < 2:
            continue

        if f" {name_norm} " not in text_box:
            continue

        exact_name_results.append(_add_meta(
            row=dict(row),
            route="LIEN_HE",
            score=100000,
            sheet="TRA_CUU_LIEN_HE",
            row_id=get_first(row, "ID", "MA", "MÃ"),
            note="NAME_MATCH_EXACT",
        ))

    if exact_name_results:
        exact_name_results.sort(
            key=lambda r: safe_int(r.get("_UU_TIEN", 999))
        )
        return exact_name_results[:limit]

    scored = []
    for row in active_rows:
        fields = _contact_field_values(row)

        if department_filter_norm and normalize_text(fields.get("bo_phan")) != department_filter_norm:
            continue

        score = 0
        notes = []

        area_score = _exact_keyword_score(user_text, fields["tdp"], 30000)
        if area_score:
            score += area_score
            notes.append("AREA_MATCH")

        keyword_score_value = _exact_keyword_score(user_text, fields["keywords"], 20000)
        if keyword_score_value:
            score += keyword_score_value
            notes.append("KEYWORD_MATCH")

        department_score = _exact_keyword_score(user_text, fields["bo_phan"], 15000)
        if department_score:
            score += department_score
            notes.append("DEPARTMENT_MATCH")

        name_score = _name_token_score(user_text, fields["name"])
        if name_score:
            score += name_score
            notes.append("NAME_MATCH")

        role_score = _exact_keyword_score(user_text, fields["role"], 10000)
        if role_score:
            score += role_score
            notes.append("ROLE_MATCH")

        if score <= 0:
            continue

        scored.append(_add_meta(
            row=row,
            route="LIEN_HE",
            score=score,
            sheet="TRA_CUU_LIEN_HE",
            row_id=get_first(row, "ID", "MA", "MÃ"),
            note="+".join(notes) or "CONTACT_MATCH",
        ))

    if not scored:
        debug_print("CONTACT", f"QUESTION: {user_text}", "NO MATCH")
        return []

    scored.sort(key=lambda r: (-safe_int(r.get("_SCORE", 0)), safe_int(r.get("_UU_TIEN", 999))))

    best_score = safe_int(scored[0].get("_SCORE", 0))
    same_group = [row for row in scored if safe_int(row.get("_SCORE", 0)) == best_score]

    if len(same_group) == 1:
        return same_group[:1]

    return same_group[:limit]

# Chức năng: Kiểm tra câu hỏi có tín hiệu rõ của thủ tục được FAQ liên kết hay không.
# Vai trò: Chặn FAQ_RELATED dẫn sang thủ tục khác khi tên hoặc TU_KHOA không khớp.
def _related_procedure_signal(user_text, related_ids):
    user_norm = normalize_text(user_text)
    user_box = f" {user_norm} "
    user_tokens = set(user_norm.split())
    resolved = False

    for related_id in split_list(related_ids):
        related_value = str(related_id or "").strip()
        related_norm = normalize_text(related_value)

        if related_norm and (
            user_norm == related_norm
            or f" {related_norm} " in user_box
        ):
            return True, True

        procedure = find_procedure_by_id(related_value)
        if not procedure:
            continue

        resolved = True
        procedure_name = normalize_text(
            get_first(procedure, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
        )

        if procedure_name and (
            user_norm == procedure_name
            or f" {procedure_name} " in user_box
        ):
            return True, True

        procedure_keywords = get_first(
            procedure,
            "TU_KHOA",
            "TỪ_KHÓA",
            "KEYWORDS",
        )

        for keyword in split_keywords(procedure_keywords):
            keyword_norm = normalize_text(keyword)
            keyword_tokens = [x for x in keyword_norm.split() if x]

            if not keyword_tokens:
                continue

            if len(keyword_tokens) >= 2 and (
                user_norm == keyword_norm
                or f" {keyword_norm} " in user_box
            ):
                return True, True

            if (
                len(keyword_tokens) == 1
                and len(keyword_norm) >= 5
                and keyword_norm in user_tokens
            ):
                return True, True

    return resolved, False

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

        if related_id and ngu_canh not in [
            "procedure_context",
            "thongtin",
            "tra_cuu_lien_he",
            "menu",
        ]:
            related_resolved, related_matched = _related_procedure_signal(
                user_text,
                related_id,
            )
            if related_resolved and not related_matched:
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
