from services.search_engine import search_lien_he, format_lien_he, format_multiple_results
from services.sheet_api import read_setting_chat


def _chat_setting(key, default=""):
    # Chức năng: Lấy nội dung cấu hình hội thoại từ sheet SETTING_CHAT.
    # Vai trò: Không để nội dung hướng dẫn liên hệ nằm cứng trong Python.
    try:
        data = read_setting_chat() or {}
        return str(data.get(key) or default or "").strip()
    except Exception:
        return str(default or "").strip()


def search_contact(question, limit=3):
    # Chức năng: Tra cứu thông tin liên hệ theo câu hỏi người dân.
    # Vai trò: Chỉ sử dụng dữ liệu TRA_CUU_LIEN_HE thông qua search_engine.
    results = search_lien_he(question, limit=limit)
    if not results:
        return None
    return format_multiple_results(results, format_lien_he, limit=limit)


def contact_router(question):
    # Chức năng: Điều phối yêu cầu tra cứu liên hệ.
    # Vai trò: Giữ contact_service là lớp gọi trung gian, không chứa nghiệp vụ.
    return search_contact(question)


def start_contact_flow(user_id=None, user_states=None):
    # Chức năng: Tạo lời hướng dẫn bắt đầu tra cứu liên hệ.
    # Vai trò: Lấy nội dung từ SETTING_CHAT.CONTACT_GUIDE thay vì hardcode trong Python.
    return _chat_setting(
        "CONTACT_GUIDE",
        "📞 TRA CỨU LIÊN HỆ\n\nQuý công dân vui lòng nhập nội dung cần tra cứu."
    )
