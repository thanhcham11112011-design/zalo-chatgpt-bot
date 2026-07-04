from datetime import datetime

from config import DEBUG_MODE
from services.sheet_api import log_chat


# Chức năng: Lấy thời gian hiện tại theo định dạng chuẩn của BOT.
# Vai trò: Thống nhất thời gian ghi LOG và LỊCH_SỬ_CHAT.
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Chức năng: Ghi lịch sử hội thoại của người dùng.
# Vai trò: Ghi toàn bộ hội thoại BOT vào Google Sheets LICH_SU_CHAT.
def write_log(user_id, user_message, bot_reply, source="BOT"):
    try:
        return log_chat(
            current_time(),
            user_id,
            user_message,
            bot_reply,
            source,
        )
    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
        return False


# Chức năng: Ghi nhật ký lỗi của BOT.
# Vai trò: Lưu lỗi phát sinh vào LICH_SU_CHAT để phục vụ kiểm tra và khắc phục.
def log_error(user_id, user_message, error_message):
    return write_log(
        user_id=user_id,
        user_message=user_message,
        bot_reply=error_message,
        source="ERROR",
    )


# Chức năng: Hiển thị thông tin DEBUG khi chạy BOT.
# Vai trò: Hỗ trợ kiểm thử và phân tích luồng xử lý trong quá trình phát triển.
def debug_log(title, data=None):
    if not DEBUG_MODE:
        return

    print("\n" + "=" * 60)
    print(f"[DEBUG] {title}")
    print("-" * 60)

    if isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}: {value}")
    elif isinstance(data, (list, tuple)):
        for item in data:
            print(item)
    elif data is not None:
        print(data)

    print("=" * 60 + "\n")
