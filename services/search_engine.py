# services/search_engine.py
# Xử lý tìm kiếm dữ liệu trong Google Sheets

import re
import unicodedata

from services.sheet_api import (
    read_menu,
    read_lien_he,
    read_faq,
    read_all_thu_tuc,
)


# =========================
# CHUẨN HÓA TEXT
# =========================

def normalize_text(text):
    if text is None:
        return ""

    text = str(text).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9\s,./:;_-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def get_first(row, *keys, default=""):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def safe_int(value, default=999):
    try:
        return int(str(value).strip())
    except Exception:
        return default


# =========================
# CHẤM ĐIỂM TỪ KHÓA
# =========================

def keyword_score(user_text, keywords):
    user_text_norm = normalize_text(user_text)
    keywords_norm = normalize_text(keywords)

    if not user_text_norm or not keywords_norm:
        return 0

    score = 0

    # Hỗ trợ cả dấu phẩy, chấm phẩy, xuống dòng
    keyword_list = [
        item.strip()
        for item in re.split(r"[,;\n]+", keywords_norm)
        if item.strip()
    ]

    for kw in keyword_list:
        if kw in user_text_norm:
            score += max(len(kw), 1)

    return score


def field_score(user_text, *fields):
    score = 0

    for field in fields:
        score += keyword_score(user_text, field)

    return score


# =========================
# TÌM MENU
# =========================

def search_menu(user_text):
    rows = read_menu()
    user_norm = normalize_text(user_text)

    results = []

    for row in rows:
        menu_id = str(row.get("ID", "")).strip()

        ten_chuc_nang = get_first(
            row,
            "TEN_CHUC_NANG",
            "TÊN_CHỨC_NĂNG",
            "TEN",
            "CHU_DE",
            "MÔ_TẢ",
            "MO_TA",
        )

        tu_khoa = get_first(row, "TU_KHOA", "TỪ_KHÓA", "TU KHOA")
        mo_ta = get_first(row, "MO_TA", "MÔ_TẢ")

        score = 0

        if user_norm == normalize_text(menu_id):
            score += 1000

        score += field_score(
            user_text,
            tu_khoa,
            ten_chuc_nang,
            mo_ta
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            results.append(row)

    results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))

    return results[0] if results else None


# =========================
# TÌM LIÊN HỆ
# =========================

def search_lien_he(user_text, limit=3):
    rows = read_lien_he()
    results = []

    for row in rows:
        score = field_score(
            user_text,
            get_first(row, "TU_KHOA", "TỪ_KHÓA"),
            get_first(row, "TDP"),
            get_first(row, "BO_PHAN", "BỘ_PHẬN"),
            get_first(row, "HỌ_TÊN", "HO_TEN", "TEN_CO_QUAN", "TÊN_CƠ_QUAN"),
            get_first(row, "CHỨC_VỤ", "CHUC_VU", "CHUC_NANG", "CHỨC_NĂNG"),
            get_first(row, "GHI_CHÚ", "GHI_CHU")
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            results.append(row)

    results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))

    return results[:limit]


# =========================
# TÌM FAQ
# =========================

def search_faq(user_text, limit=3):
    rows = read_faq()
    results = []

    for row in rows:
        score = field_score(
            user_text,
            get_first(row, "TU_KHOA", "TỪ_KHÓA"),
            get_first(row, "CAU_HOI", "CÂU_HỎI"),
            get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRA_LOI_DAY_DU")
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(get_first(row, "UU_TIEN", "MUC_UU_TIEN", default=999))
            results.append(row)

    results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))

    return results[:limit]


# =========================
# TÌM THỦ TỤC
# =========================

def search_thu_tuc(user_text, limit=5):
    rows = read_all_thu_tuc()
    results = []

    for row in rows:
        score = field_score(
            user_text,
            get_first(row, "TU_KHOA", "TỪ_KHÓA"),
            get_first(row, "CHU_DE", "CHỦ_ĐỀ"),
            get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC"),
            get_first(row, "MO_TA", "MÔ_TẢ"),
            get_first(row, "GOI_Y_CAU_HOI", "GỢI_Ý_CÂU_HỎI"),
            get_first(row, "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN")
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(
                get_first(row, "MUC_UU_TIEN", "UU_TIEN", default=999)
            )
            results.append(row)

    results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))

    return results[:limit]


# =========================
# FORMAT TRẢ LỜI
# =========================

def format_lien_he(row):
    ten = get_first(row, "TEN_CO_QUAN", "TÊN_CƠ_QUAN", "HỌ_TÊN", "HO_TEN")
    bo_phan = get_first(row, "BO_PHAN", "BỘ_PHẬN")
    tdp = get_first(row, "TDP")
    chuc_nang = get_first(row, "CHUC_NANG", "CHỨC_NĂNG", "CHỨC_VỤ", "CHUC_VU")
    phone = get_first(row, "SO_DIEN_THOAI", "ĐIỆN_THOẠI", "DIEN_THOAI")
    email = get_first(row, "EMAIL")
    map_link = get_first(row, "GOOGLE_MAP", "MAP")
    note = get_first(row, "GHI_CHU", "GHI_CHÚ")

    parts = []

    if ten:
        parts.append(f"📌 {ten}")

    if chuc_nang:
        parts.append(f"Chức vụ/chức năng: {chuc_nang}")

    if bo_phan:
        parts.append(f"Bộ phận: {bo_phan}")

    if tdp:
        parts.append(f"Địa bàn/TDP: {tdp}")

    if phone:
        parts.append(f"Điện thoại: {phone}")

    if email:
        parts.append(f"Email: {email}")

    if note:
        parts.append(f"Ghi chú: {note}")

    if map_link:
        parts.append(f"Bản đồ: {map_link}")

    return "\n".join(parts)


def format_faq(row):
    cau_hoi = get_first(row, "CAU_HOI", "CÂU_HỎI")
    tra_loi = get_first(row, "TRA_LOI", "TRẢ_LỜI", "TRA_LOI_NGAN", "TRẢ_LỜI_NGẮN", "TRA_LOI_DAY_DU", "TRẢ_LỜI_ĐẦY_ĐỦ")

    if cau_hoi and tra_loi:
        return f"❓ {cau_hoi}\n\n{tra_loi}"

    return tra_loi or cau_hoi


def format_thu_tuc(row):
    ten = get_first(row, "TEN_THU_TUC", "TÊN_THỦ_TỤC")
    mo_ta = get_first(row, "MO_TA", "MÔ_TẢ")
    doi_tuong = get_first(row, "DOI_TUONG_AP_DUNG", "ĐỐI_TƯỢNG_ÁP_DỤNG")
    dieu_kien = get_first(row, "DIEU_KIEN", "ĐIỀU_KIỆN")
    ho_so = get_first(row, "HO_SO", "HỒ_SƠ")
    trinh_tu = get_first(row, "TRINH_TU", "TRÌNH_TỰ")
    noi_nop = get_first(row, "NOI_NOP", "NƠI_NỘP", "CO_QUAN_THUC_HIEN", "CƠ_QUAN_THỰC_HIỆN")
    thoi_han = get_first(row, "THOI_HAN", "THỜI_HẠN")
    le_phi = get_first(row, "LE_PHI", "LỆ_PHÍ")
    ket_qua = get_first(row, "KET_QUA", "KẾT_QUẢ")
    luu_y = get_first(row, "LUU_Y", "LƯU_Ý")
    link = get_first(row, "LINK_DVC")

    parts = []

    if ten:
        parts.append(f"📄 {ten}")

    if mo_ta:
        parts.append(f"Mô tả: {mo_ta}")

    if doi_tuong:
        parts.append(f"Đối tượng: {doi_tuong}")

    if dieu_kien:
        parts.append(f"Điều kiện: {dieu_kien}")

    if ho_so:
        parts.append(f"Hồ sơ: {ho_so}")

    if trinh_tu:
        parts.append(f"Trình tự: {trinh_tu}")

    if noi_nop:
        parts.append(f"Nơi nộp/cơ quan thực hiện: {noi_nop}")

    if thoi_han:
        parts.append(f"Thời hạn: {thoi_han}")

    if le_phi:
        parts.append(f"Lệ phí: {le_phi}")

    if ket_qua:
        parts.append(f"Kết quả: {ket_qua}")

    if luu_y:
        parts.append(f"Lưu ý: {luu_y}")

    if link:
        parts.append(f"Link DVC: {link}")

    return "\n".join(parts)


def format_multiple_results(results, formatter, limit=3):
    selected = results[:limit]
    texts = []

    for index, row in enumerate(selected, start=1):
        formatted = formatter(row)
        if formatted:
            texts.append(f"{index}. {formatted}")

    return "\n\n".join(texts)
