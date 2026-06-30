# sheet_api.py
# Đọc dữ liệu Google Sheets cho BOT Công an phường Phù Liễn

import os
import re
import unicodedata
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


# =========================
# CẤU HÌNH CHUNG
# =========================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")


SHEET_NAMES = {
    "MENU": "MENU",
    "SETTING_SYSTEM": "SETTING_SYSTEM",
    "SETTING_AI": "SETTING_AI",
    "SETTING_CHAT": "SETTING_CHAT",
    "PROMPT": "PROMPT",
    "THONGTIN": "THONGTIN",
    "TRA_CUU_LIEN_HE": "TRA_CUU_LIEN_HE",
    "FAQ": "FAQ",
    "LICH_SU_CHAT": "LICH_SU_CHAT",

    "THU_TUC_CCCD": "THU_TUC_CCCD",
    "THU_TUC_CUTRU": "THU_TUC_CUTRU",
    "THU_TUC_VNEID": "THU_TUC_VNEID",
    "THU_TUC_LLTP": "THU_TUC_LLTP",
    "THU_TUC_PTGT": "THU_TUC_PTGT",
    "THU_TUC_PCCC": "THU_TUC_PCCC",
    "THU_TUC_VKVLN": "THU_TUC_VKVLN",
    "THU_TUC_ANTT": "THU_TUC_ANTT",
}

THU_TUC_SHEETS = [
    "THU_TUC_CCCD",
    "THU_TUC_CUTRU",
    "THU_TUC_VNEID",
    "THU_TUC_LLTP",
    "THU_TUC_PTGT",
    "THU_TUC_PCCC",
    "THU_TUC_VKVLN",
    "THU_TUC_ANTT",
]


# =========================
# KẾT NỐI GOOGLE SHEET
# =========================

def get_client():
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_spreadsheet():
    if not SPREADSHEET_ID:
        raise ValueError("Chưa cấu hình SPREADSHEET_ID trong biến môi trường.")
    client = get_client()
    return client.open_by_key(SPREADSHEET_ID)


def get_worksheet(sheet_name):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)


# =========================
# TIỆN ÍCH XỬ LÝ TEXT
# =========================

def normalize_text(text):
    """
    Chuẩn hóa tiếng Việt:
    - chuyển thường
    - bỏ dấu
    - xóa ký tự thừa
    """
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


def is_on(row):
    """
    Chỉ dùng dòng có TRANG_THAI = ON.
    Nếu sheet chưa có cột TRANG_THAI thì mặc định dùng.
    """
    status = str(row.get("TRANG_THAI", "ON")).strip().upper()
    return status == "ON"


def safe_int(value, default=999):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def keyword_match(user_text, keywords):
    """
    So khớp từ khóa trong cột TU_KHOA.
    """
    user_text_norm = normalize_text(user_text)
    keywords_norm = normalize_text(keywords)

    if not user_text_norm or not keywords_norm:
        return False

    keyword_list = [
        kw.strip()
        for kw in keywords_norm.split(",")
        if kw.strip()
    ]

    for kw in keyword_list:
        if kw in user_text_norm:
            return True

    return False


def score_keyword_match(user_text, keywords):
    """
    Chấm điểm theo số từ khóa khớp.
    """
    user_text_norm = normalize_text(user_text)
    keywords_norm = normalize_text(keywords)

    if not user_text_norm or not keywords_norm:
        return 0

    score = 0
    keyword_list = [
        kw.strip()
        for kw in keywords_norm.split(",")
        if kw.strip()
    ]

    for kw in keyword_list:
        if kw in user_text_norm:
            score += len(kw)

    return score


# =========================
# ĐỌC SHEET CƠ BẢN
# =========================

def read_sheet(sheet_name):
    """
    Đọc toàn bộ sheet thành list dict.
    """
    try:
        ws = get_worksheet(sheet_name)
        rows = ws.get_all_records()
        return rows
    except Exception as e:
        print(f"[ERROR] Không đọc được sheet {sheet_name}: {e}")
        return []


def read_active_rows(sheet_name):
    """
    Đọc sheet và chỉ lấy dòng TRANG_THAI = ON.
    """
    rows = read_sheet(sheet_name)
    return [row for row in rows if is_on(row)]


# =========================
# ĐỌC SETTING
# =========================

def get_settings(sheet_name):
    """
    Dùng cho SETTING_SYSTEM, SETTING_AI, SETTING_CHAT.
    Cấu trúc khuyến nghị:
    KEY | VALUE | DESCRIPTION | TRANG_THAI
    """
    rows = read_active_rows(sheet_name)
    settings = {}

    for row in rows:
        key = str(row.get("KEY", "")).strip()
        value = row.get("VALUE", "")

        if key:
            settings[key] = value

    return settings


def get_system_settings():
    return get_settings("SETTING_SYSTEM")


def get_ai_settings():
    return get_settings("SETTING_AI")


def get_chat_settings():
    return get_settings("SETTING_CHAT")


# =========================
# ĐỌC PROMPT
# =========================

def get_prompts():
    """
    Cấu trúc khuyến nghị:
    PROMPT_NAME | NOI_DUNG | TRANG_THAI
    """
    rows = read_active_rows("PROMPT")
    prompts = {}

    for row in rows:
        name = str(row.get("PROMPT_NAME", "")).strip()
        content = str(row.get("NOI_DUNG", "")).strip()

        if name:
            prompts[name] = content

    return prompts


def get_prompt(prompt_name, default=""):
    prompts = get_prompts()
    return prompts.get(prompt_name, default)


# =========================
# MENU
# =========================

def get_menu():
    return read_active_rows("MENU")


def find_menu(user_text):
    """
    Tìm menu theo TU_KHOA hoặc ID.
    """
    rows = get_menu()
    user_norm = normalize_text(user_text)

    matches = []

    for row in rows:
        menu_id = str(row.get("ID", "")).strip()
        keywords = row.get("TU_KHOA", "")

        if user_norm == normalize_text(menu_id):
            matches.append(row)
            continue

        if keyword_match(user_text, keywords):
            row["_score"] = score_keyword_match(user_text, keywords)
            matches.append(row)

    matches.sort(key=lambda x: x.get("_score", 0), reverse=True)

    return matches[0] if matches else None


# =========================
# THÔNG TIN ĐƠN VỊ
# =========================

def get_thongtin():
    """
    Cấu trúc khuyến nghị:
    KEY | VALUE | GHI_CHU | TRANG_THAI
    """
    rows = read_active_rows("THONGTIN")
    info = {}

    for row in rows:
        key = str(row.get("KEY", "")).strip()
        value = row.get("VALUE", "")

        if key:
            info[key] = value

    return info


# =========================
# TRA CỨU LIÊN HỆ
# =========================

def get_lien_he():
    return read_active_rows("TRA_CUU_LIEN_HE")


def search_lien_he(user_text, limit=3):
    """
    Sheet TRA_CUU_LIEN_HE gồm 10 cột:
    BO_PHAN
    TDP
    TU_KHOA
    TEN_CO_QUAN
    CHUC_NANG
    SO_DIEN_THOAI
    GOOGLE_MAP
    GHI_CHU
    TRANG_THAI
    UU_TIEN
    """
    rows = get_lien_he()
    results = []

    for row in rows:
        keywords = row.get("TU_KHOA", "")
        ten = row.get("TEN_CO_QUAN", "")
        chuc_nang = row.get("CHUC_NANG", "")
        tdp = row.get("TDP", "")

        score = 0
        score += score_keyword_match(user_text, keywords)
        score += score_keyword_match(user_text, ten)
        score += score_keyword_match(user_text, chuc_nang)
        score += score_keyword_match(user_text, tdp)

        if score > 0:
            row["_score"] = score
            row["_uu_tien"] = safe_int(row.get("UU_TIEN", 999))
            results.append(row)

    results.sort(key=lambda x: (x["_uu_tien"], -x["_score"]))

    return results[:limit]


# =========================
# FAQ
# =========================

def get_faq():
    return read_active_rows("FAQ")


def search_faq(user_text, limit=3):
    rows = get_faq()
    results = []

    for row in rows:
        keywords = row.get("TU_KHOA", "")
        cau_hoi = row.get("CAU_HOI", "")
        tra_loi = row.get("TRA_LOI", "")

        score = 0
        score += score_keyword_match(user_text, keywords)
        score += score_keyword_match(user_text, cau_hoi)

        if score > 0:
            row["_score"] = score
            results.append(row)

    results.sort(key=lambda x: x["_score"], reverse=True)

    return results[:limit]


# =========================
# THỦ TỤC HÀNH CHÍNH
# =========================

def get_thu_tuc_by_sheet(sheet_name):
    return read_active_rows(sheet_name)


def get_all_thu_tuc():
    all_rows = []

    for sheet in THU_TUC_SHEETS:
        rows = read_active_rows(sheet)

        for row in rows:
            row["_sheet"] = sheet
            all_rows.append(row)

    return all_rows


def search_thu_tuc(user_text, limit=5):
    """
    Tìm thủ tục theo:
    TU_KHOA
    TEN_THU_TUC
    CHU_DE
    TRA_LOI_NGAN
    TRA_LOI_DAY_DU
    """
    rows = get_all_thu_tuc()
    results = []

    for row in rows:
        score = 0

        score += score_keyword_match(user_text, row.get("TU_KHOA", ""))
        score += score_keyword_match(user_text, row.get("TEN_THU_TUC", ""))
        score += score_keyword_match(user_text, row.get("CHU_DE", ""))
        score += score_keyword_match(user_text, row.get("TRA_LOI_NGAN", ""))
        score += score_keyword_match(user_text, row.get("GOI_Y_CAU_HOI", ""))

        if score > 0:
            row["_score"] = score
            row["_uu_tien"] = safe_int(row.get("MUC_UU_TIEN", 999))
            results.append(row)

    results.sort(key=lambda x: (x["_uu_tien"], -x["_score"]))

    return results[:limit]


# =========================
# FORMAT CÂU TRẢ LỜI
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


def format_thu_tuc(row):
    ten = row.get("TEN_THU_TUC", "")
    mo_ta = row.get("MO_TA", "")
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


def format_faq(row):
    question = row.get("CAU_HOI", "")
    answer = row.get("TRA_LOI", "")

    if question and answer:
        return f"❓ {question}\n\n{answer}"

    return answer or question


# =========================
# GHI LỊCH SỬ CHAT
# =========================

def log_chat(user_id, user_message, bot_reply, source="BOT"):
    """
    Ghi vào sheet LICH_SU_CHAT.

    Cột khuyến nghị:
    THOI_GIAN | USER_ID | USER_MESSAGE | BOT_REPLY | SOURCE
    """
    try:
        ws = get_worksheet("LICH_SU_CHAT")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        ws.append_row([
            now,
            user_id,
            user_message,
            bot_reply,
            source
        ])

        return True

    except Exception as e:
        print(f"[ERROR] Không ghi được LICH_SU_CHAT: {e}")
        return False


# =========================
# HÀM KIỂM TRA KẾT NỐI
# =========================

def test_connection():
    try:
        spreadsheet = get_spreadsheet()
        print("✅ Kết nối Google Sheet thành công.")
        print("Tên file:", spreadsheet.title)

        for name in SHEET_NAMES.values():
            try:
                ws = spreadsheet.worksheet(name)
                print(f"✅ {name}: {ws.row_count} dòng")
            except Exception:
                print(f"❌ Không tìm thấy sheet: {name}")

        return True

    except Exception as e:
        print("❌ Lỗi kết nối Google Sheet:", e)
        return False


if __name__ == "__main__":
    test_connection()
