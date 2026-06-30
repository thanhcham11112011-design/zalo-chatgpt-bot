# logger.py
# Ghi lịch sử chat vào Google Sheet

from datetime import datetime

from sheet_api import log_chat


def current_time():
    """
    Trả về thời gian hiện tại.
    Định dạng: YYYY-MM-DD HH:MM:SS
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_log(
    user_id,
    user_message,
    bot_reply,
    source="BOT"
):
    """
    Ghi 01 bản ghi vào sheet LICH_SU_CHAT
    """

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


def log_menu(user_id, user_message, bot_reply):
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=bot_reply,
        source="MENU"
    )


def log_faq(user_id, user_message, bot_reply):
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=bot_reply,
        source="FAQ"
    )


def log_thu_tuc(user_id, user_message, bot_reply):
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=bot_reply,
        source="THU_TUC"
    )


def log_lien_he(user_id, user_message, bot_reply):
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=bot_reply,
        source="TRA_CUU_LIEN_HE"
    )


def log_ai(user_id, user_message, bot_reply):
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=bot_reply,
        source="GEMINI_AI"
    )


def log_error(user_id, user_message, error_message):
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=error_message,
        source="ERROR"
    )


if __name__ == "__main__":

    ok = write_log(
        user_id="TEST_USER",
        user_message="Xin chào",
        bot_reply="Đây là bản ghi kiểm tra.",
        source="TEST"
    )

    if ok:
        print("✅ Ghi log thành công")
    else:
        print("❌ Ghi log thất bại")
