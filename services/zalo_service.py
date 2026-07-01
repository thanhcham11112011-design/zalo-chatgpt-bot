# services/zalo_service.py

import os
import json
import threading
from datetime import datetime, timedelta, timezone

import requests
import gspread
from google.oauth2.service_account import Credentials

ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v2.0/oa/message"
ZALO_REFRESH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"

SETTING_SHEET_NAME = "SETTING_SYSTEM"

ZALO_APP_ID = os.getenv("ZALO_APP_ID", "")
ZALO_APP_SECRET = os.getenv("ZALO_APP_SECRET", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

_token_lock = threading.Lock()
_current_access_token = None
_current_refresh_token = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_setting_ws():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(GOOGLE_SHEET_ID)
    return sh.worksheet(SETTING_SHEET_NAME)


def _load_settings():
    ws = _get_setting_ws()
    rows = ws.get_all_records()
    data = {}

    for row in rows:
        key = str(row.get("KEY", "")).strip()
        value = str(row.get("VALUE", "")).strip()
        status = str(row.get("STATUS", "ON")).strip().upper()

        if key and status == "ON":
            data[key] = value

    return data


def _update_setting(key, value):
    ws = _get_setting_ws()
    values = ws.get_all_values()

    if not values:
        return False

    header = values[0]
    key_col = header.index("KEY") + 1
    value_col = header.index("VALUE") + 1

    for i, row in enumerate(values[1:], start=2):
        if len(row) >= key_col and row[key_col - 1].strip() == key:
            ws.update_cell(i, value_col, value)
            return True

    ws.append_row([key, value, "", "ON"])
    return True


def _load_tokens_from_sheet():
    global _current_access_token, _current_refresh_token

    settings = _load_settings()
    _current_access_token = settings.get("ZALO_ACCESS_TOKEN")
    _current_refresh_token = settings.get("ZALO_REFRESH_TOKEN")

    return bool(_current_access_token and _current_refresh_token)


def refresh_zalo_access_token():
    global _current_access_token, _current_refresh_token

    with _token_lock:
        if not _current_refresh_token:
            _load_tokens_from_sheet()

        if not ZALO_APP_ID or not ZALO_APP_SECRET or not _current_refresh_token:
            print("[ZALO REFRESH ERROR] Thiếu APP_ID / APP_SECRET / REFRESH_TOKEN")
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
                timeout=15,
            )

            result = response.json()

            if response.status_code == 200 and result.get("access_token"):
                new_access_token = result.get("access_token")
                new_refresh_token = result.get("refresh_token") or _current_refresh_token
                expires_in = int(result.get("expires_in", 86400))

                _current_access_token = new_access_token
                _current_refresh_token = new_refresh_token

                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                _update_setting("ZALO_ACCESS_TOKEN", new_access_token)
                _update_setting("ZALO_REFRESH_TOKEN", new_refresh_token)
                _update_setting("ZALO_TOKEN_STATUS", "OK")
                _update_setting("ZALO_TOKEN_UPDATED_AT", _now_iso())
                _update_setting("ZALO_TOKEN_EXPIRES_AT", expires_at.isoformat())

                print("[ZALO REFRESH] Thành công, đã lưu token mới vào SETTING_SYSTEM")
                return True

            _update_setting("ZALO_TOKEN_STATUS", f"ERROR: {result}")
            print("[ZALO REFRESH ERROR]", result)
            return False

        except Exception as e:
            _update_setting("ZALO_TOKEN_STATUS", f"EXCEPTION: {e}")
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
            data = {"error": "invalid_json", "text": response.text}

        if response.status_code == 200 and data.get("error") == 0:
            return True, data

        return False, data

    except Exception as e:
        return False, {"error": "request_exception", "message": str(e)}


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
