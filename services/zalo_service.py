# services/zalo_service.py
# Gửi tin nhắn Zalo OA + tự động refresh token, lưu token mới vào SETTING_SYSTEM

import os
import threading
from datetime import datetime, timedelta, timezone

import requests

from services.sheet_api import (
    read_setting_system,
    update_setting_system,
)

ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v2.0/oa/message"
ZALO_REFRESH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"

_token_lock = threading.Lock()
_current_access_token = None
_current_refresh_token = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_app_config():
    """
    APP_ID / APP_SECRET ưu tiên lấy từ SETTING_SYSTEM.
    Nếu chưa có trên Sheet thì lấy từ Render Environment.
    """
    settings = read_setting_system()
    app_id = str(settings.get("ZALO_APP_ID") or os.getenv("ZALO_APP_ID", "")).strip()
    app_secret = str(settings.get("ZALO_APP_SECRET") or os.getenv("ZALO_APP_SECRET", "")).strip()
    return app_id, app_secret, settings


def _load_tokens_from_sheet():
    global _current_access_token, _current_refresh_token

    settings = read_setting_system()

    _current_access_token = str(
        settings.get("ZALO_ACCESS_TOKEN") or os.getenv("ZALO_ACCESS_TOKEN", "")
    ).strip()

    _current_refresh_token = str(
        settings.get("ZALO_REFRESH_TOKEN") or os.getenv("ZALO_REFRESH_TOKEN", "")
    ).strip()

    return bool(_current_access_token and _current_refresh_token)


def refresh_zalo_access_token():
    global _current_access_token, _current_refresh_token

    with _token_lock:
        if not _current_refresh_token:
            _load_tokens_from_sheet()

        app_id, app_secret, _ = _get_app_config()

        if not app_id or not app_secret or not _current_refresh_token:
            print("[ZALO REFRESH ERROR] Thiếu ZALO_APP_ID / ZALO_APP_SECRET / ZALO_REFRESH_TOKEN")
            update_setting_system("ZALO_TOKEN_STATUS", "ERROR: MISSING_APP_OR_REFRESH_TOKEN")
            return False

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "secret_key": app_secret,
        }

        data = {
            "app_id": app_id,
            "grant_type": "refresh_token",
            "refresh_token": _current_refresh_token,
        }

        try:
            response = requests.post(
                ZALO_REFRESH_TOKEN_URL,
                headers=headers,
                data=data,
                timeout=15,
            )

            try:
                result = response.json()
            except Exception:
                result = {
                    "error": "invalid_json",
                    "status_code": response.status_code,
                    "text": response.text[:500],
                }

            if response.status_code == 200 and result.get("access_token"):
                new_access_token = str(result.get("access_token", "")).strip()
                new_refresh_token = str(result.get("refresh_token") or _current_refresh_token).strip()

                try:
                    expires_in = int(result.get("expires_in", 86400))
                except Exception:
                    expires_in = 86400

                _current_access_token = new_access_token
                _current_refresh_token = new_refresh_token

                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                update_setting_system("ZALO_ACCESS_TOKEN", new_access_token)
                update_setting_system("ZALO_REFRESH_TOKEN", new_refresh_token)
                update_setting_system("ZALO_TOKEN_STATUS", "OK")
                update_setting_system("ZALO_TOKEN_UPDATED_AT", _now_iso())
                update_setting_system("ZALO_TOKEN_EXPIRES_AT", expires_at.isoformat())

                print("[ZALO REFRESH] Thành công, đã lưu token mới vào SETTING_SYSTEM")
                return True

            update_setting_system("ZALO_TOKEN_STATUS", f"ERROR: {result}")
            print("[ZALO REFRESH ERROR]", result)
            return False

        except Exception as e:
            update_setting_system("ZALO_TOKEN_STATUS", f"EXCEPTION: {e}")
            print("[ZALO REFRESH EXCEPTION]", e)
            return False


def _send_text_once(user_id, message):
    global _current_access_token

    if not _current_access_token:
        _load_tokens_from_sheet()

    if not _current_access_token:
        return False, {"error": "missing_access_token"}

    headers = {
        "Content-Type": "application/json",
        "access_token": _current_access_token,
    }

    payload = {
        "recipient": {"user_id": str(user_id)},
        "message": {"text": str(message)[:2000]},
    }

    try:
        response = requests.post(
            ZALO_SEND_MESSAGE_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )

        try:
            data = response.json()
        except Exception:
            data = {
                "error": "invalid_json",
                "status_code": response.status_code,
                "text": response.text[:500],
            }

        if response.status_code == 200 and data.get("error") == 0:
            return True, data

        return False, data

    except Exception as e:
        return False, {
            "error": "request_exception",
            "message": str(e),
        }


def send_zalo_text(user_id, message):
    if not user_id:
        print("[ZALO ERROR] Thiếu user_id")
        return False

    if not message:
        print("[ZALO ERROR] Nội dung rỗng")
        return False

    if not _current_access_token or not _current_refresh_token:
        _load_tokens_from_sheet()

    ok, data = _send_text_once(user_id, message)

    if ok:
        return True

    # -216: access token invalid/expired
    if data.get("error") == -216:
        print("[ZALO TOKEN] Access Token hết hạn, đang refresh...")

        if refresh_zalo_access_token():
            ok_retry, data_retry = _send_text_once(user_id, message)

            if ok_retry:
                return True

            print("[ZALO ERROR AFTER REFRESH]", data_retry)
            return False

    print("[ZALO ERROR]", data)
    return False


def send_text(user_id, text):
    return send_zalo_text(user_id, text)
