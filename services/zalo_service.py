# services/zalo_service.py
# Gửi tin nhắn Zalo OA + tự động refresh Access Token khi hết hạn

import requests

from config import (
    ZALO_ACCESS_TOKEN,
    ZALO_REFRESH_TOKEN,
    ZALO_APP_ID,
    ZALO_APP_SECRET,
)


ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v2.0/oa/message"
ZALO_REFRESH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"

_current_access_token = ZALO_ACCESS_TOKEN
_current_refresh_token = ZALO_REFRESH_TOKEN


def refresh_zalo_access_token():
    global _current_access_token
    global _current_refresh_token

    if not ZALO_APP_ID or not ZALO_APP_SECRET or not _current_refresh_token:
        print("[ZALO REFRESH ERROR] Thiếu ZALO_APP_ID / ZALO_APP_SECRET / ZALO_REFRESH_TOKEN")
        return False

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "secret_key": ZALO_APP_SECRET,
    }

    data = {
        "app_id": ZALO_APP_ID,
        "grant_type": "refresh_token",
        "refresh_token": _current_refresh_token,
    }

    try:
        response = requests.post(
            ZALO_REFRESH_TOKEN_URL,
            headers=headers,
            data=data,
            timeout=15
        )

        result = response.json()

        if response.status_code == 200 and result.get("access_token"):
            _current_access_token = result.get("access_token")
            new_refresh_token = result.get("refresh_token")

            if new_refresh_token:
                _current_refresh_token = new_refresh_token

            print("[ZALO REFRESH] Lấy Access Token mới thành công")
            return True

        print("[ZALO REFRESH ERROR]", result)
        return False

    except Exception as e:
        print(f"[ZALO REFRESH ERROR] {e}")
        return False


def _send_text_once(user_id, message):
    if not _current_access_token:
        print("[ZALO ERROR] Thiếu ZALO_ACCESS_TOKEN")
        return False, {"error": "missing_access_token"}

    headers = {
        "Content-Type": "application/json",
        "access_token": _current_access_token,
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

        try:
            data = response.json()
        except Exception:
            data = {
                "error": "invalid_json",
                "text": response.text
            }

        if response.status_code == 200 and data.get("error") == 0:
            return True, data

        return False, data

    except Exception as e:
        return False, {
            "error": "request_exception",
            "message": str(e)
        }


def send_zalo_text(user_id, message):
    if not user_id:
        print("[ZALO ERROR] Thiếu user_id")
        return False

    if not message:
        print("[ZALO ERROR] Nội dung tin nhắn rỗng")
        return False

    ok, data = _send_text_once(user_id, message)

    if ok:
        return True

    # -216 = Access token expired
    if data.get("error") == -216:
        print("[ZALO TOKEN] Access Token hết hạn, đang refresh...")

        refreshed = refresh_zalo_access_token()

        if refreshed:
            ok_retry, data_retry = _send_text_once(user_id, message)

            if ok_retry:
                return True

            print("[ZALO ERROR AFTER REFRESH]", data_retry)
            return False

    print("[ZALO ERROR]", data)
    return False


def send_text(user_id, text):
    return send_zalo_text(user_id, text)
