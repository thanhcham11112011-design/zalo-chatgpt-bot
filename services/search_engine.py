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
    text = re.sub(r"[^a-z0-9\s,./:-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


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

    keyword_list = [
        item.strip()
        for item in keywords_norm.split(",")
        if item.strip()
    ]

    for kw in keyword_list:
        if kw in user_text_norm:
            score += len(kw)

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

        ten_chuc_nang = (
            row.get("TEN_CHUC_NANG")
            or row.get("TEN")
            or row.get("CHU_DE")
            or ""
        )

        tu_khoa = row.get("TU_KHOA", "")
        mo_ta = row.get("MO_TA", "")

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
            row["_UU_TIEN"] = safe_int(row.get("UU_TIEN", 999))
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
            row.get("TU_KHOA", ""),
            row.get("TDP", ""),
            row.get("TEN_CO_QUAN", ""),
            row.get("CHUC_NANG", ""),
            row.get("GHI_CHU", "")
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(row.get("UU_TIEN", 999))
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
            row.get("TU_KHOA", ""),
            row.get("CAU_HOI", ""),
            row.get("TRA_LOI", "")
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(row.get("UU_TIEN", 999))
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
            row.get("TU_KHOA", ""),
            row.get("CHU_DE", ""),
            row.get("TEN_THU_TUC", ""),
            row.get("MO_TA", ""),
            row.get("GOI_Y_CAU_HOI", ""),
            row.get("TRA_LOI_NGAN", "")
        )

        if score > 0:
            row["_SCORE"] = score
            row["_UU_TIEN"] = safe_int(
                row.get("MUC_UU_TIEN", row.get("UU_TIEN", 999))
            )
            results.append(row)

    results.sort(key=lambda x: (x["_UU_TIEN"], -x["_SCORE"]))

    return results[:limit]


# =========================
# FORMAT TRẢ LỜI
# =========================

def format_lien_he(row):
    ten = row.get("TEN_CO_QUAN", "")
    chuc_nang = row.get("CHUC_NANG", "")
    phone = row.get("SO_DIEN_THOAI", "")
    map_link = row.get("GOOGLE_MAP", "")
    note = row.get("GHI_CHU", "")

    parts = []

    if ten:
        parts.append(f"📌 {ten}")

    if chuc_nang:
        parts.append(f"Chức năng: {chuc_nang}")

    if phone:
        parts.append(f"Điện thoại: {phone}")

    if note:
        parts.append(f"Ghi chú: {note}")

    if map_link:
        parts.append(f"Bản đồ: {map_link}")

    return "\n".join(parts)


def format_faq(row):
    cau_hoi = row.get("CAU_HOI", "")
    tra_loi = row.get("TRA_LOI", "")

    if cau_hoi and tra_loi:
        return f"❓ {cau_hoi}\n\n{tra_loi}"

    return tra_loi or cau_hoi


def format_thu_tuc(row):
    ten = row.get("TEN_THU_TUC", "")
    mo_ta = row.get("MO_TA", "")
    doi_tuong = row.get("DOI_TUONG_AP_DUNG", "")
    dieu_kien = row.get("DIEU_KIEN", "")
    ho_so = row.get("HO_SO", "")
    trinh_tu = row.get("TRINH_TU", "")
    noi_nop = row.get("NOI_NOP", "")
    thoi_han = row.get("THOI_HAN", "")
    le_phi = row.get("LE_PHI", "")
    ket_qua = row.get("KET_QUA", "")
    luu_y = row.get("LUU_Y", "")
    link = row.get("LINK_DVC", "")

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
        parts.append(f"Nơi nộp: {noi_nop}")

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
        texts.append(f"{index}. {formatter(row)}")

    return "\n\n".join(texts)
