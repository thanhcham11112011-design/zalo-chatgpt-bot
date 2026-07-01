import os
import threading
from datetime import datetime, timedelta, timezone
import requests
from config import MAX_ZALO_TEXT_LENGTH
from services.sheet_api import read_setting_system, update_setting_system

ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v2.0/oa/message"
ZALO_REFRESH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
_token_lock = threading.Lock()
_current_access_token = None
_current_refresh_token = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_app_config():
    settings = read_setting_system()
    app_id = str(settings.get("ZALO_APP_ID") or os.getenv("ZALO_APP_ID", "")).strip()
    app_secret = str(settings.get("ZALO_APP_SECRET") or os.getenv("ZALO_APP_SECRET", "")).strip()
    return app_id, app_secret


def _load_tokens_from_sheet():
    global _current_access_token, _current_refresh_token
    settings = read_setting_system()
    _current_access_token = str(settings.get("ZALO_ACCESS_TOKEN") or os.getenv("ZALO_ACCESS_TOKEN", "")).strip()
    _current_refresh_token = str(settings.get("ZALO_REFRESH_TOKEN") or os.getenv("ZALO_REFRESH_TOKEN", "")).strip()
    return bool(_current_access_token and _current_refresh_token)


def refresh_zalo_access_token():
    global _current_access_token, _current_refresh_token
    with _token_lock:
        if not _current_refresh_token:
            _load_tokens_from_sheet()
        app_id, app_secret = _get_app_config()
        if not app_id or not app_secret or not _current_refresh_token:
            print("[ZALO REFRESH ERROR] Thiếu APP_ID / APP_SECRET / REFRESH_TOKEN")
            update_setting_system("ZALO_TOKEN_STATUS", "ERROR: MISSING_CONFIG")
            return False
        try:
            response = requests.post(
                ZALO_REFRESH_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded", "secret_key": app_secret},
                data={"app_id": app_id, "grant_type": "refresh_token", "refresh_token": _current_refresh_token},
                timeout=15,
            )
            try:
                data = response.json()
            except Exception:
                data = {"error": "invalid_json", "status_code": response.status_code, "text": response.text[:500]}
            if response.status_code == 200 and data.get("access_token"):
                _current_access_token = str(data.get("access_token", "")).strip()
                _current_refresh_token = str(data.get("refresh_token") or _current_refresh_token).strip()
                expires_in = int(data.get("expires_in", 86400) or 86400)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                update_setting_system("ZALO_ACCESS_TOKEN", _current_access_token)
                update_setting_system("ZALO_REFRESH_TOKEN", _current_refresh_token)
                update_setting_system("ZALO_TOKEN_STATUS", "OK")
                update_setting_system("ZALO_TOKEN_UPDATED_AT", _now_iso())
                update_setting_system("ZALO_TOKEN_EXPIRES_AT", expires_at.isoformat())
                print("[ZALO REFRESH] Thành công")
                return True
            update_setting_system("ZALO_TOKEN_STATUS", f"ERROR: {data}")
            print("[ZALO REFRESH ERROR]", data)
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
    payload = {"recipient": {"user_id": str(user_id)}, "message": {"text": str(message)[:MAX_ZALO_TEXT_LENGTH]}}
    try:
        response = requests.post(
            ZALO_SEND_MESSAGE_URL,
            headers={"Content-Type": "application/json", "access_token": _current_access_token},
            json=payload,
            timeout=15,
        )
        try:
            data = response.json()
        except Exception:
            data = {"error": "invalid_json", "status_code": response.status_code, "text": response.text[:500]}
        return response.status_code == 200 and data.get("error") == 0, data
    except Exception as e:
        return False, {"error": "request_exception", "message": str(e)}


def send_zalo_text(user_id, message):
    if not user_id or not message:
        return False
    if not _current_access_token or not _current_refresh_token:
        _load_tokens_from_sheet()
    ok, data = _send_text_once(user_id, message)
    if ok:
        return True
    if data.get("error") == -216:
        print("[ZALO TOKEN] Access Token hết hạn, refresh...")
        if refresh_zalo_access_token():
            ok2, data2 = _send_text_once(user_id, message)
            if ok2:
                return True
            print("[ZALO ERROR AFTER REFRESH]", data2)
            return False
    print("[ZALO ERROR]", data)
    return False


def send_text(user_id, text):
    return send_zalo_text(user_id, text)
