import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

import requests

from config import MAX_ZALO_TEXT_LENGTH
from services.sheet_api import read_setting_system, update_setting_system

ZALO_SEND_MESSAGE_URL = "https://openapi.zalo.me/v2.0/oa/message"
ZALO_REFRESH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"

_token_lock = threading.Lock()
_settings_lock = threading.Lock()
_persist_retry_lock = threading.Lock()

_current_access_token = ""
_current_refresh_token = ""
_settings_cache: Dict[str, str] = {}
_settings_loaded = False
_last_refresh_failure_at = 0.0
_persist_retry_running = False

ZALO_REFRESH_FAILURE_COOLDOWN_SECONDS = max(
    int(os.getenv("ZALO_REFRESH_FAILURE_COOLDOWN_SECONDS", "60")),
    1,
)


# Chức năng: Lấy thời gian hiện tại theo chuẩn ISO UTC.
# Vai trò: Ghi mốc cập nhật token Zalo phục vụ vận hành hệ thống.
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Chức năng: Chuẩn hóa chuỗi cấu hình kỹ thuật.
# Vai trò: Tránh lỗi khi đọc dữ liệu từ biến môi trường hoặc Google Sheets.
def _clean(value: Any) -> str:
    return str(value or "").strip()


# Chức năng: Nạp một lần nhóm cấu hình Zalo từ SETTING_SYSTEM.
# Vai trò: Giảm số lần đọc Google Sheets khi gửi và làm mới token.
def _load_zalo_settings(force: bool = False) -> Dict[str, str]:
    global _settings_cache, _settings_loaded

    with _settings_lock:
        if _settings_loaded and not force:
            return dict(_settings_cache)

        try:
            sheet_settings = read_setting_system() or {}
        except Exception as e:
            print("[ZALO SETTINGS READ ERROR]", e)
            sheet_settings = {}

        keys = (
            "ZALO_APP_ID",
            "ZALO_APP_SECRET",
            "ZALO_ACCESS_TOKEN",
            "ZALO_REFRESH_TOKEN",
        )

        loaded = {}

        for key in keys:
            value = _clean(
                sheet_settings.get(key)
                or os.getenv(key, "")
            )

            if value:
                loaded[key] = value
            elif key in _settings_cache:
                loaded[key] = _settings_cache[key]

        _settings_cache.update(loaded)
        _settings_loaded = True
        return dict(_settings_cache)


# Chức năng: Lấy cấu hình ứng dụng Zalo từ bộ nhớ cấu hình đã nạp.
# Vai trò: Cung cấp app_id và app_secret mà không đọc Sheet riêng từng khóa.
def _get_app_config(force: bool = False) -> Tuple[str, str]:
    settings = _load_zalo_settings(force=force)
    return (
        _clean(settings.get("ZALO_APP_ID")),
        _clean(settings.get("ZALO_APP_SECRET")),
    )


# Chức năng: Nạp access token và refresh token vào bộ nhớ tiến trình.
# Vai trò: Chỉ đọc SETTING_SYSTEM khi chưa có token hoặc khi buộc đồng bộ lại.
def _load_tokens(force: bool = False) -> bool:
    global _current_access_token, _current_refresh_token

    settings = _load_zalo_settings(force=force)
    access_token = _clean(settings.get("ZALO_ACCESS_TOKEN"))
    refresh_token = _clean(settings.get("ZALO_REFRESH_TOKEN"))

    if access_token:
        _current_access_token = access_token

    if refresh_token:
        _current_refresh_token = refresh_token

    return bool(_current_access_token)


# Chức năng: Cập nhật cache cấu hình sau khi Zalo cấp cặp token mới.
# Vai trò: Giữ token trong RAM đồng nhất mà không phải đọc lại Google Sheets.
def _update_token_cache(access_token: str, refresh_token: str) -> None:
    global _settings_cache, _settings_loaded

    with _settings_lock:
        _settings_cache["ZALO_ACCESS_TOKEN"] = _clean(access_token)
        _settings_cache["ZALO_REFRESH_TOKEN"] = _clean(refresh_token)
        _settings_loaded = True


# Chức năng: Lưu cặp token mới vào SETTING_SYSTEM theo thứ tự an toàn.
# Vai trò: Ưu tiên lưu refresh token trước để tránh mất khả năng tự cấp access token lần sau.
def _persist_token_values(
    access_token: str,
    refresh_token: str,
    expires_at: str,
) -> bool:
    refresh_saved = update_setting_system(
        "ZALO_REFRESH_TOKEN",
        _clean(refresh_token),
    )

    if not refresh_saved:
        print("[ZALO TOKEN SAVE ERROR] Không lưu được refresh token mới")
        return False

    access_saved = update_setting_system(
        "ZALO_ACCESS_TOKEN",
        _clean(access_token),
    )

    if not access_saved:
        print("[ZALO TOKEN SAVE ERROR] Không lưu được access token mới")
        return False

    update_setting_system("ZALO_TOKEN_STATUS", "OK")
    update_setting_system("ZALO_TOKEN_UPDATED_AT", _now_iso())
    update_setting_system(
        "ZALO_TOKEN_EXPIRES_AT",
        _clean(expires_at),
    )
    return True


# Chức năng: Thử lưu lại cặp token trong nền khi Google Sheets tạm thời lỗi.
# Vai trò: Không chặn phản hồi Zalo nhưng vẫn bảo vệ refresh token mới sau lỗi quota.
def _retry_persist_tokens(
    access_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    global _persist_retry_running

    try:
        for delay_seconds in (15, 30, 60, 120):
            time.sleep(delay_seconds)

            with _token_lock:
                is_current_pair = (
                    _current_access_token == access_token
                    and _current_refresh_token == refresh_token
                )

            if not is_current_pair:
                return

            if _persist_token_values(
                access_token,
                refresh_token,
                expires_at,
            ):
                print("[ZALO TOKEN] Đã lưu lại token sau lỗi tạm thời")
                return

    finally:
        with _persist_retry_lock:
            _persist_retry_running = False


# Chức năng: Khởi động một luồng thử lưu token mà không tạo trùng luồng.
# Vai trò: Giới hạn số lần ghi lại Google Sheets khi hệ thống đang vượt quota.
def _schedule_token_persist_retry(
    access_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    global _persist_retry_running

    with _persist_retry_lock:
        if _persist_retry_running:
            return

        _persist_retry_running = True

    worker = threading.Thread(
        target=_retry_persist_tokens,
        args=(access_token, refresh_token, expires_at),
        daemon=True,
        name="zalo-token-persist",
    )
    worker.start()


# Chức năng: Lưu trạng thái lỗi token Zalo theo cơ chế giới hạn ghi.
# Vai trò: Ghi dấu vận hành nhưng không làm lỗi Sheet cản luồng gửi tin.
def _save_token_error_status(note: str) -> None:
    try:
        update_setting_system("ZALO_TOKEN_STATUS", "ERROR")
        update_setting_system(
            "ZALO_TOKEN_NOTE",
            _clean(note)[:500],
        )
    except Exception as e:
        print("[ZALO TOKEN STATUS ERROR]", e)


# Chức năng: Refresh access token Zalo bằng refresh token hiện có.
# Vai trò: Chống refresh đồng thời, lưu refresh token mới và duy trì gửi tin khi access token hết hạn.
def refresh_zalo_access_token(
    failed_access_token: str = "",
) -> bool:
    global _current_access_token
    global _current_refresh_token
    global _last_refresh_failure_at

    with _token_lock:
        failed_token = _clean(failed_access_token)

        if (
            failed_token
            and _current_access_token
            and _current_access_token != failed_token
        ):
            return True

        now = time.monotonic()

        if (
            _last_refresh_failure_at
            and now - _last_refresh_failure_at
            < ZALO_REFRESH_FAILURE_COOLDOWN_SECONDS
        ):
            print("[ZALO REFRESH SKIPPED] Đang trong thời gian chờ sau lỗi refresh")
            return False

        if not _current_refresh_token:
            _load_tokens()

        app_id, app_secret = _get_app_config()

        if (
            not app_id
            or not app_secret
            or not _current_refresh_token
        ):
            _last_refresh_failure_at = now
            _save_token_error_status(
                "MISSING_APP_CONFIG_OR_REFRESH_TOKEN"
            )
            print(
                "[ZALO REFRESH ERROR] "
                "Thiếu APP_ID / APP_SECRET / REFRESH_TOKEN"
            )
            return False

        refresh_token_used = _current_refresh_token

        try:
            response = requests.post(
                ZALO_REFRESH_TOKEN_URL,
                headers={
                    "Content-Type": (
                        "application/x-www-form-urlencoded"
                    ),
                    "secret_key": app_secret,
                },
                data={
                    "app_id": app_id,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token_used,
                },
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

            if (
                response.status_code == 200
                and data.get("access_token")
            ):
                new_access_token = _clean(
                    data.get("access_token")
                )
                new_refresh_token = _clean(
                    data.get("refresh_token")
                    or refresh_token_used
                )
                expires_in = int(
                    data.get("expires_in", 86400)
                    or 86400
                )
                expires_at = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=expires_in)
                ).isoformat(timespec="seconds")

                _current_access_token = new_access_token
                _current_refresh_token = new_refresh_token
                _last_refresh_failure_at = 0.0

                _update_token_cache(
                    new_access_token,
                    new_refresh_token,
                )

                saved = _persist_token_values(
                    new_access_token,
                    new_refresh_token,
                    expires_at,
                )

                if not saved:
                    _schedule_token_persist_retry(
                        new_access_token,
                        new_refresh_token,
                        expires_at,
                    )

                return True

            refreshed_settings = _load_zalo_settings(force=True)
            latest_refresh_token = _clean(
                refreshed_settings.get("ZALO_REFRESH_TOKEN")
            )

            if (
                latest_refresh_token
                and latest_refresh_token != refresh_token_used
            ):
                _current_refresh_token = latest_refresh_token
                print(
                    "[ZALO TOKEN] Phát hiện refresh token mới "
                    "trong SETTING_SYSTEM, thử lại một lần"
                )

                retry_response = requests.post(
                    ZALO_REFRESH_TOKEN_URL,
                    headers={
                        "Content-Type": (
                            "application/x-www-form-urlencoded"
                        ),
                        "secret_key": app_secret,
                    },
                    data={
                        "app_id": app_id,
                        "grant_type": "refresh_token",
                        "refresh_token": latest_refresh_token,
                    },
                    timeout=15,
                )

                try:
                    retry_data = retry_response.json()
                except Exception:
                    retry_data = {
                        "error": "invalid_json",
                        "status_code": retry_response.status_code,
                        "text": retry_response.text[:500],
                    }

                if (
                    retry_response.status_code == 200
                    and retry_data.get("access_token")
                ):
                    new_access_token = _clean(
                        retry_data.get("access_token")
                    )
                    new_refresh_token = _clean(
                        retry_data.get("refresh_token")
                        or latest_refresh_token
                    )
                    expires_in = int(
                        retry_data.get("expires_in", 86400)
                        or 86400
                    )
                    expires_at = (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=expires_in)
                    ).isoformat(timespec="seconds")

                    _current_access_token = new_access_token
                    _current_refresh_token = new_refresh_token
                    _last_refresh_failure_at = 0.0

                    _update_token_cache(
                        new_access_token,
                        new_refresh_token,
                    )

                    saved = _persist_token_values(
                        new_access_token,
                        new_refresh_token,
                        expires_at,
                    )

                    if not saved:
                        _schedule_token_persist_retry(
                            new_access_token,
                            new_refresh_token,
                            expires_at,
                        )

                    return True

                data = retry_data

            _last_refresh_failure_at = time.monotonic()
            _save_token_error_status(str(data))
            print("[ZALO REFRESH ERROR]", data)
            return False

        except Exception as e:
            _last_refresh_failure_at = time.monotonic()
            _save_token_error_status(str(e))
            print("[ZALO REFRESH EXCEPTION]", e)
            return False


# Chức năng: Cắt nội dung tin nhắn theo giới hạn kỹ thuật của Zalo.
# Vai trò: Tránh lỗi gửi tin do nội dung vượt quá độ dài cấu hình.
def _trim_message(message: Any) -> str:
    text = _clean(message)
    limit = max(int(MAX_ZALO_TEXT_LENGTH or 1900), 1)
    return text[:limit]


# Chức năng: Gửi một tin nhắn Zalo một lần bằng access token hiện tại.
# Vai trò: Trả lại token đã sử dụng để chống refresh lặp giữa nhiều thread.
def _send_text_once(
    user_id: str,
    message: str,
) -> Tuple[bool, Dict[str, Any], str]:
    global _current_access_token

    if not _current_access_token:
        _load_tokens()

    access_token_used = _clean(_current_access_token)

    if not access_token_used:
        return (
            False,
            {"error": "missing_access_token"},
            "",
        )

    payload = {
        "recipient": {
            "user_id": _clean(user_id),
        },
        "message": {
            "text": _trim_message(message),
        },
    }

    try:
        response = requests.post(
            ZALO_SEND_MESSAGE_URL,
            headers={
                "Content-Type": "application/json",
                "access_token": access_token_used,
            },
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

        ok = (
            response.status_code == 200
            and data.get("error") == 0
        )
        return ok, data, access_token_used

    except Exception as e:
        return (
            False,
            {
                "error": "request_exception",
                "message": str(e),
            },
            access_token_used,
        )


# Chức năng: Gửi tin nhắn văn bản về Zalo OA.
# Vai trò: Tự refresh một lần khi token hết hạn và không refresh trùng giữa các thread.
def send_zalo_text(user_id: str, message: str) -> bool:
    if not _clean(user_id) or not _clean(message):
        return False

    ok, data, token_used = _send_text_once(
        user_id,
        message,
    )

    if ok:
        return True

    if data.get("error") == -216:
        print(
            "[ZALO TOKEN] "
            "Access token hết hạn, đang refresh"
        )

        if refresh_zalo_access_token(
            failed_access_token=token_used,
        ):
            (
                ok_after_refresh,
                data_after_refresh,
                _,
            ) = _send_text_once(
                user_id,
                message,
            )

            if ok_after_refresh:
                return True

            print(
                "[ZALO ERROR AFTER REFRESH]",
                data_after_refresh,
            )
            return False

    print("[ZALO ERROR]", data)
    return False


# Chức năng: Alias gửi tin nhắn văn bản.
# Vai trò: Giữ tương thích với các module cũ đang gọi send_text.
def send_text(user_id: str, text: str) -> bool:
    return send_zalo_text(user_id, text)
