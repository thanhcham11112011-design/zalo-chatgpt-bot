# services/zalo_service.py
# Gửi tin nhắn Zalo OA

import requests

from config import ZALO_ACCESS_TOKEN


ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v3.0/oa/message/cs"


def send_zalo_text(user_id, message):
    if not ZALO_ACCESS_TOKEN:
        print("[ZALO ERROR] Thiếu ZALO_ACCESS_TOKEN")
        return False

    if not user_id:
        print("[ZALO ERROR] Thiếu user_id")
        return False

    if not message:
        print("[ZALO ERROR] Nội dung tin nhắn rỗng")
        return False

    headers = {
        "Content-Type": "application/json",
        "access_token": ZALO_ACCESS_TOKEN,
    }

    payload = {
        "recipient": {
            "user_id": str(user_id)
        },
        "message": {
            "text": str(message)[:2000]
        }
    }

    try:
        response = requests.post(
            ZALO_SEND_MESSAGE_URL,
            headers=headers,
            json=payload,
            timeout=15
        )

        data = response.json()

        if response.status_code == 200 and data.get("error") == 0:
            return True

        print("[ZALO ERROR]", data)
        return False

    except Exception as e:
        print(f"[ZALO ERROR] {e}")
        return False


# Giữ tương thích nếu code cũ còn gọi zalo_service.send_text(...)
def send_text(user_id, text):
    return send_zalo_text(user_id, text)
