# services/contact_service.py
# Tra cứu thông tin liên hệ từ sheet TRA_CUU_LIEN_HE

from services.search_engine import (
    search_lien_he,
    format_lien_he,
    format_multiple_results,
)


def search_contact(question, limit=3):
    results = search_lien_he(
        question,
        limit=limit
    )

    if not results:
        return None

    return format_multiple_results(
        results,
        format_lien_he,
        limit=limit
    )


def contact_router(question):
    return search_contact(question)


def start_contact_flow(user_id=None, user_states=None):
    return (
        "📞 TRA CỨU LIÊN HỆ\n\n"
        "Quý công dân vui lòng nhập nội dung cần tra cứu.\n\n"
        "Ví dụ:\n"
        "• Số điện thoại trực ban\n"
        "• Công an phường Phù Liễn\n"
        "• Làm căn cước ở đâu\n"
        "• Đăng ký xe ở đâu\n"
        "• Lý lịch tư pháp\n"
        "• PCCC"
    )
