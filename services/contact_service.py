# services/contact_service.py
# Tra cứu thông tin liên hệ

from services.search_engine import (
    search_lien_he,
    format_lien_he,
    format_multiple_results,
)


def search_contact(question, limit=3):
    """
    Tra cứu thông tin liên hệ từ sheet TRA_CUU_LIEN_HE.
    """
    results = search_lien_he(question, limit=limit)

    if not results:
        return None

    return format_multiple_results(
        results,
        format_lien_he,
        limit=limit
    )


def start_contact_flow(user_id=None, user_states=None):
    """
    Giữ tương thích với code cũ.
    """
    return (
        "📞 Tra cứu thông tin liên hệ\n\n"
        "Vui lòng nhập nội dung cần tra cứu.\n\n"
        "Ví dụ:\n"
        "• Số điện thoại trực ban\n"
        "• Công an phường Phù Liễn\n"
        "• Căn cước\n"
        "• Đăng ký xe\n"
        "• Lý lịch tư pháp"
    )


def contact_router(question):
    """
    Router chuyên cho tra cứu liên hệ.
    """
    return search_contact(question)
