import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

import requests

from config import MAX_ZALO_TEXT_LENGTH
from services.sheet_api import read_setting_system, update_setting_system

ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v2.0/oa/message"
ZALO_REFRESH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"

_token_lock = threading.Lock()
_current_access_token = None
_current_refresh_token = None


# Chức năng: Lấy thời gian hiện tại theo chuẩn ISO UTC.
# Vai trò: Ghi mốc cập nhật token Zalo phục vụ vận hành hệ thống.
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Chức năng: Chuẩn hóa chuỗi cấu hình kỹ thuật.
# Vai trò: Tránh lỗi khi đọc dữ liệu từ biến môi trường hoặc Google Sheets.
def _clean(value: Any) -> str:
    return str(value or "").strip()


# Chức năng: Lấy một cấu hình kỹ thuật theo thứ tự Google Sheets rồi biến môi trường.
# Vai trò: Cho phép vận hành token Zalo linh hoạt mà không gắn nghiệp vụ vào code.
def _setting(key: str, env_key: str = "") -> str:
    try:
        settings = read_setting_system() or {}
    except Exception:
        settings = {}
    return _clean(settings.get(key) or os.getenv(env_key or key, ""))


# Chức năng: Lấy cấu hình ứng dụng Zalo từ SETTING_SYSTEM hoặc biến môi trường.
# Vai trò: Cung cấp app_id và app_secret cho luồng refresh token.
def _get_app_config() -> Tuple[str, str]:
    return _setting("ZALO_APP_ID"), _setting("ZALO_APP_SECRET")


# Chức năng: Nạp access token và refresh token từ SETTING_SYSTEM hoặc biến môi trường.
# Vai trò: Chuẩn bị thông tin xác thực để gửi tin nhắn Zalo.
def _load_tokens() -> bool:
    global _current_access_token, _current_refresh_token
    _current_access_token = _setting("ZALO_ACCESS_TOKEN")
    _current_refresh_token = _setting("ZALO_REFRESH_TOKEN")
    return bool(_current_access_token)


# Chức năng: Lưu trạng thái token Zalo vào SETTING_SYSTEM.
# Vai trò: Hỗ trợ theo dõi lỗi vận hành mà không ảnh hưởng luồng trả lời nghiệp vụ.
def _save_token_status(status: str, note: str = "") -> None:
    update_setting_system("ZALO_TOKEN_STATUS", _clean(status))
    update_setting_system("ZALO_TOKEN_UPDATED_AT", _now_iso())
    if note:
        update_setting_system("ZALO_TOKEN_NOTE", _clean(note)[:500])


# Chức năng: Refresh access token Zalo bằng refresh token hiện có.
# Vai trò: Duy trì khả năng gửi tin nhắn Zalo khi access token hết hạn.
def refresh_zalo_access_token() -> bool:
    global _current_access_token, _current_refresh_token

    with _token_lock:
        if not _current_refresh_token:
            _load_tokens()

        app_id, app_secret = _get_app_config()
        if not app_id or not app_secret or not _current_refresh_token:
            _save_token_status("ERROR", "MISSING_APP_CONFIG_OR_REFRESH_TOKEN")
            print("[ZALO REFRESH ERROR] Thiếu APP_ID / APP_SECRET / REFRESH_TOKEN")
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
                _current_access_token = _clean(data.get("access_token"))
                _current_refresh_token = _clean(data.get("refresh_token") or _current_refresh_token)
                expires_in = int(data.get("expires_in", 86400) or 86400)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                update_setting_system("ZALO_ACCESS_TOKEN", _current_access_token)
                update_setting_system("ZALO_REFRESH_TOKEN", _current_refresh_token)
                update_setting_system("ZALO_TOKEN_STATUS", "OK")
                update_setting_system("ZALO_TOKEN_UPDATED_AT", _now_iso())
                update_setting_system("ZALO_TOKEN_EXPIRES_AT", expires_at.isoformat(timespec="seconds"))
                return True

            _save_token_status("ERROR", str(data))
            print("[ZALO REFRESH ERROR]", data)
            return False

        except Exception as e:
            _save_token_status("EXCEPTION", str(e))
            print("[ZALO REFRESH EXCEPTION]", e)
            return False


# Chức năng: Cắt nội dung tin nhắn theo giới hạn kỹ thuật của Zalo.
# Vai trò: Tránh lỗi gửi tin do nội dung vượt quá độ dài cấu hình.
def _trim_message(message: Any) -> str:
    text = _clean(message)
    limit = max(int(MAX_ZALO_TEXT_LENGTH or 1900), 1)
    return text[:limit]


# Chức năng: Gửi một tin nhắn Zalo một lần bằng access token hiện tại.
# Vai trò: Tách bước gửi thật khỏi cơ chế retry/refresh token.
def _send_text_once(user_id: str, message: str) -> Tuple[bool, Dict[str, Any]]:
    global _current_access_token

    if not _current_access_token:
        _load_tokens()

    if not _current_access_token:
        return False, {"error": "missing_access_token"}

    payload = {"recipient": {"user_id": _clean(user_id)}, "message": {"text": _trim_message(message)}}

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


# Chức năng: Gửi tin nhắn văn bản về Zalo OA.
# Vai trò: Là cổng gửi tin duy nhất từ BOT sang Zalo, không chứa nghiệp vụ trả lời.
def send_zalo_text(user_id: str, message: str) -> bool:
    if not _clean(user_id) or not _clean(message):
        return False

    if not _current_access_token:
        _load_tokens()

    ok, data = _send_text_once(user_id, message)
    if ok:
        return True

    if data.get("error") == -216:
        print("[ZALO TOKEN] Access token hết hạn, đang refresh")
        if refresh_zalo_access_token():
            ok_after_refresh, data_after_refresh = _send_text_once(user_id, message)
            if ok_after_refresh:
                return True
            print("[ZALO ERROR AFTER REFRESH]", data_after_refresh)
            return False

    print("[ZALO ERROR]", data)
    return False


# Chức năng: Alias gửi tin nhắn văn bản.
# Vai trò: Giữ tương thích với các module cũ đang gọi send_text.
def send_text(user_id: str, text: str) -> bool:
    return send_zalo_text(user_id, text)
