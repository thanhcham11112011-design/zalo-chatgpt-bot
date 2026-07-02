from datetime import datetime
from config import DEBUG_MODE
from services.sheet_api import log_chat


def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_log(user_id, user_message, bot_reply, source="BOT"):
    try:
        return log_chat(current_time(), user_id, user_message, bot_reply, source)
    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
        return False


def log_error(user_id, user_message, error_message):
    return write_log(user_id, user_message, error_message, "ERROR")
def debug_log(title, data=None):
    if not DEBUG_MODE:
        return

    print("\n================ DEBUG BOT CAP ================")
    print(f"[{title}]")

    if isinstance(data, dict):
        for k, v in data.items():
            print(f"{k}: {v}")
    elif data is not None:
        print(data)

    print("================================================\n")
