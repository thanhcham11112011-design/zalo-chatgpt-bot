# services/logger.py
# Ghi lịch sử hội thoại vào Google Sheet

from datetime import datetime

from services.sheet_api import log_chat


# ==========================================
# THỜI GIAN HIỆN TẠI
# ==========================================

def current_time():
    """
    Định dạng:
    YYYY-MM-DD HH:MM:SS
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==========================================
# GHI LOG CHUNG
# ==========================================

def write_log(
    user_id,
    user_message,
    bot_reply,
    source="BOT"
):
    try:

        return log_chat(
            thoi_gian=current_time(),
            user_id=user_id,
            user_message=user_message,
            bot_reply=bot_reply,
            source=source
        )

    except Exception as e:

        print(f"[LOGGER ERROR] {e}")

        return False


# ==========================================
# CÁC LOẠI LOG
# ==========================================

def log_menu(user_id, user_message, bot_reply):
    return write_log(
        user_id,
        user_message,
        bot_reply,
        "MENU"
    )


def log_faq(user_id, user_message, bot_reply):
    return write_log(
        user_id,
        user_message,
        bot_reply,
        "FAQ"
    )


def log_thu_tuc(user_id, user_message, bot_reply):
    return write_log(
        user_id,
        user_message,
        bot_reply,
        "THU_TUC"
    )


def log_lien_he(user_id, user_message, bot_reply):
    return write_log(
        user_id,
        user_message,
        bot_reply,
        "TRA_CUU_LIEN_HE"
    )


def log_ai(user_id, user_message, bot_reply):
    return write_log(
        user_id,
        user_message,
        bot_reply,
        "GEMINI_AI"
    )


def log_error(user_id, user_message, error_message):
    return write_log(
        user_id,
        user_message,
        error_message,
        "ERROR"
    )


# ==========================================
# TEST
# ==========================================

if __name__ == "__main__":

    ok = write_log(
        user_id="TEST_USER",
        user_message="Xin chào",
        bot_reply="Đây là bản ghi kiểm tra",
        source="TEST"
    )

    if ok:
        print("✅ Logger OK")
    else:
        print("❌ Logger Error")
