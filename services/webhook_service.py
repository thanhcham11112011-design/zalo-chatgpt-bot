import hashlib
import hmac
from typing import Any, Dict


# Chức năng: Chuẩn hóa giá trị kỹ thuật trong payload webhook.
# Vai trò: Bảo đảm khóa chống trùng và chữ ký không bị sai do None hoặc khoảng trắng.
def _clean(value: Any) -> str:
    return str(value or "").strip()


# Chức năng: Tạo khóa duy nhất cho một sự kiện Zalo gửi đến BOT.
# Vai trò: Ưu tiên msg_id; khi thiếu msg_id dùng người gửi, loại sự kiện, thời gian và nội dung.
def build_webhook_event_key(
    message_id: Any,
    user_id: Any,
    event_name: Any,
    event_timestamp: Any,
    question: Any,
) -> str:
    clean_message_id = _clean(message_id)

    if clean_message_id:
        return f"msg:{clean_message_id}"

    fallback_parts = (
        _clean(user_id),
        _clean(event_name),
        _clean(event_timestamp),
        _clean(question),
    )

    if not all(fallback_parts):
        return ""

    fallback_source = "\x1f".join(fallback_parts)
    fallback_hash = hashlib.sha256(
        fallback_source.encode("utf-8")
    ).hexdigest()
    return f"fallback:{fallback_hash}"


# Chức năng: Tạo mã băm ngắn cho nội dung câu hỏi.
# Vai trò: Hỗ trợ đối chiếu sự kiện mà không lưu thêm nội dung người dùng vào sheet kỹ thuật.
def question_hash(question: Any) -> str:
    return hashlib.sha256(
        _clean(question).encode("utf-8")
    ).hexdigest()


# Chức năng: Xác thực chữ ký X-ZEvent-Signature của Zalo OA.
# Vai trò: Chỉ cho phép payload thật từ Zalo đi vào router và tầng gửi tin nhắn.
def verify_zalo_webhook_signature(
    raw_body: Any,
    payload: Dict[str, Any],
    provided_signature: Any,
    oa_secret_key: Any,
    expected_app_id: Any = "",
    header_timestamp: Any = "",
) -> bool:
    signature = _clean(provided_signature).lower()
    secret_key = _clean(oa_secret_key)

    if signature.startswith("mac="):
        signature = signature.split("=", 1)[1].strip()

    if not signature or not secret_key:
        return False

    data = payload if isinstance(payload, dict) else {}
    payload_app_id = _clean(data.get("app_id"))
    configured_app_id = _clean(expected_app_id)
    app_id = payload_app_id or configured_app_id
    timestamp = _clean(header_timestamp) or _clean(
        data.get("timestamp")
    )

    if not app_id or not timestamp:
        return False

    if configured_app_id and payload_app_id != configured_app_id:
        return False

    try:
        if isinstance(raw_body, bytes):
            raw_text = raw_body.decode("utf-8")
        else:
            raw_text = str(raw_body or "")
    except UnicodeDecodeError:
        return False

    signature_source = (
        app_id
        + raw_text
        + timestamp
        + secret_key
    )
    expected_signature = hashlib.sha256(
        signature_source.encode("utf-8")
    ).hexdigest()

    return hmac.compare_digest(
        signature,
        expected_signature,
    )
