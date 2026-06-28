import requests

from config import (
    ZALO_ACCESS_TOKEN,
    MAX_REPLY_LENGTH,
)


ZALO_API_URL = "https://openapi.zalo.me/v2.0/oa/message"


class ZaloService:
    def __init__(self):
        self.access_token = ZALO_ACCESS_TOKEN

        if not self.access_token:
            print("ZALO WARNING: Thiếu ZALO_ACCESS_TOKEN")

    def send_text(self, user_id, text):
        if not self.access_token:
            print("ZALO ERROR: Thiếu access token")
            return False

        if not user_id:
            print("ZALO ERROR: Thiếu user_id")
            return False

        if not text:
            text = "Xin lỗi, hệ thống chưa có nội dung phản hồi."

        text = str(text)

        if len(text) > MAX_REPLY_LENGTH:
            text = text[:MAX_REPLY_LENGTH]

        headers = {
            "access_token": self.access_token,
            "Content-Type": "application/json",
        }

        payload = {
            "recipient": {
                "user_id": str(user_id)
            },
            "message": {
                "text": text
            }
        }

        try:
            response = requests.post(
                ZALO_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )

            print("ZALO STATUS:", response.status_code)
            print("ZALO RESPONSE:", response.text)

            if response.status_code == 200:
                data = response.json()

                if data.get("error", 0) == 0:
                    return True

                return False

            return False

        except Exception as e:
            print("ZALO SEND ERROR:", e)
            return False


zalo_service = ZaloService()
