import requests

from config import (
    ZALO_ACCESS_TOKEN,
    ZALO_REFRESH_TOKEN,
    ZALO_APP_ID,
    ZALO_APP_SECRET,
    MAX_REPLY_LENGTH,
)

ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v2.0/oa/message"
ZALO_REFRESH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"


class ZaloService:
    def __init__(self):
        self.access_token = ZALO_ACCESS_TOKEN
        self.refresh_token = ZALO_REFRESH_TOKEN
        self.app_id = ZALO_APP_ID
        self.app_secret = ZALO_APP_SECRET

    def refresh_access_token(self):
        if not self.refresh_token or not self.app_id or not self.app_secret:
            print("ZALO REFRESH ERROR: Thiếu refresh_token / app_id / app_secret")
            return False

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "secret_key": self.app_secret,
        }

        data = {
            "refresh_token": self.refresh_token,
            "app_id": self.app_id,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(
                ZALO_REFRESH_TOKEN_URL,
                headers=headers,
                data=data,
                timeout=30
            )

            print("ZALO REFRESH STATUS:", response.status_code)
            print("ZALO REFRESH RESPONSE:", response.text)

            result = response.json()

            new_access_token = result.get("access_token")
            new_refresh_token = result.get("refresh_token")

            if not new_access_token:
                return False

            self.access_token = new_access_token

            if new_refresh_token:
                self.refresh_token = new_refresh_token

            print("ZALO REFRESH SUCCESS")
            return True

        except Exception as e:
            print("ZALO REFRESH EXCEPTION:", e)
            return False

    def _send_text_once(self, user_id, text):
        if not self.access_token:
            print("ZALO ERROR: Thiếu access_token, thử refresh...")
            if not self.refresh_access_token():
                return False, None

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

        response = requests.post(
            ZALO_SEND_MESSAGE_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        print("ZALO STATUS:", response.status_code)
        print("ZALO RESPONSE:", response.text)

        try:
            return response.status_code == 200, response.json()
        except Exception:
            return response.status_code == 200, None

    def send_text(self, user_id, text):
        text = str(text or "Xin lỗi, hệ thống chưa có nội dung phản hồi.")

        if len(text) > MAX_REPLY_LENGTH:
            text = text[:MAX_REPLY_LENGTH]

        try:
            success, result = self._send_text_once(user_id, text)

            if success and result and result.get("error") == 0:
                return True

            error_code = None
            if isinstance(result, dict):
                error_code = result.get("error")

            if error_code == -216:
                print("ZALO TOKEN EXPIRED: Đang làm mới access token...")

                if self.refresh_access_token():
                    success, result = self._send_text_once(user_id, text)

                    if success and result and result.get("error") == 0:
                        return True

            return False

        except Exception as e:
            print("ZALO SEND ERROR:", e)
            return False


zalo_service = ZaloService()
