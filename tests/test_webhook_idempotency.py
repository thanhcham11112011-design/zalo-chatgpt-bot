import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from services import sheet_api
from services.webhook_service import (
    build_webhook_event_key,
    question_hash,
    verify_zalo_webhook_signature,
)


class FakeWebhookWorksheet:
    # Chức năng: Mô phỏng sheet BOT_WEBHOOK_EVENT trong bộ nhớ.
    # Vai trò: Kiểm tra chống trùng bền vững mà không gọi Google Sheets thật.
    def __init__(self):
        self.rows = [list(sheet_api.WEBHOOK_EVENT_HEADERS)]

    def get_all_values(self):
        return [list(row) for row in self.rows]

    def append_row(self, row):
        self.rows.append(list(row))

    def delete_rows(self, start, end=None):
        end = end or start
        del self.rows[start - 1:end]


def test_webhook_signature_accepts_official_formula():
    payload = {
        "app_id": "app-01",
        "timestamp": "1784192400000",
        "event_name": "user_send_text",
    }
    raw_body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    secret = "oa-secret"
    signature = hashlib.sha256(
        (
            payload["app_id"]
            + raw_body
            + payload["timestamp"]
            + secret
        ).encode("utf-8")
    ).hexdigest()

    assert verify_zalo_webhook_signature(
        raw_body=raw_body,
        payload=payload,
        provided_signature=signature,
        oa_secret_key=secret,
        expected_app_id="app-01",
    ) is True


def test_webhook_signature_rejects_wrong_signature():
    payload = {
        "app_id": "app-01",
        "timestamp": "1784192400000",
    }

    assert verify_zalo_webhook_signature(
        raw_body=json.dumps(payload),
        payload=payload,
        provided_signature="invalid",
        oa_secret_key="oa-secret",
        expected_app_id="app-01",
    ) is False


def test_fallback_event_key_is_stable_and_private():
    first = build_webhook_event_key(
        message_id="",
        user_id="user-01",
        event_name="user_send_text",
        event_timestamp="1784192400000",
        question="Cho tôi xin số điện thoại công an khu vực",
    )
    second = build_webhook_event_key(
        message_id="",
        user_id="user-01",
        event_name="user_send_text",
        event_timestamp="1784192400000",
        question="Cho tôi xin số điện thoại công an khu vực",
    )

    assert first == second
    assert first.startswith("fallback:")
    assert "điện thoại" not in first
    assert len(question_hash("nội dung")) == 64


def test_register_webhook_event_survives_memory_reset(monkeypatch):
    worksheet = FakeWebhookWorksheet()
    monkeypatch.setattr(
        sheet_api,
        "ensure_webhook_event_sheet",
        lambda: worksheet,
    )
    sheet_api._reset_webhook_event_cache()

    first = sheet_api.register_webhook_event(
        event_key="msg:restart-01",
        message_id="restart-01",
    )
    sheet_api._reset_webhook_event_cache()
    second = sheet_api.register_webhook_event(
        event_key="msg:restart-01",
        message_id="restart-01",
    )

    assert first == "NEW"
    assert second == "DUPLICATE"
    assert len(worksheet.rows) == 2
    sheet_api._reset_webhook_event_cache()


def test_remember_message_is_atomic_for_concurrent_duplicates(
    reset_message_dedup,
):
    import app

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                app.remember_message,
                ["msg:parallel-01"] * 20,
            )
        )

    assert results.count(False) == 1
    assert results.count(True) == 19


def test_webhook_persistent_duplicate_does_not_send_again(
    monkeypatch,
    reset_message_dedup,
):
    import app

    persistent_keys = set()
    build_calls = []
    send_calls = []

    def fake_register(**kwargs):
        event_key = kwargs["event_key"]
        if event_key in persistent_keys:
            return "DUPLICATE"
        persistent_keys.add(event_key)
        return "NEW"

    monkeypatch.setattr(app, "ZALO_WEBHOOK_VERIFY_SIGNATURE", False)
    monkeypatch.setattr(app, "register_webhook_event", fake_register)
    monkeypatch.setattr(
        app,
        "build_answer",
        lambda **kwargs: build_calls.append(kwargs) or ("Kết quả", "TEST"),
    )
    monkeypatch.setattr(
        app,
        "send_zalo_text",
        lambda **kwargs: send_calls.append(kwargs) or True,
    )
    client = app.app.test_client()
    payload = {
        "event_name": "user_send_text",
        "timestamp": "1784192400000",
        "sender": {"id": "user-01"},
        "message": {
            "msg_id": "restart-02",
            "text": "menu",
        },
    }

    first = client.post("/webhook", json=payload)
    app.processed_messages.clear()
    second = client.post("/webhook", json=payload)

    assert first.get_json()["success"] is True
    assert second.get_json()["message"] == "Duplicate ignored"
    assert len(build_calls) == 1
    assert len(send_calls) == 1


def test_webhook_missing_identity_is_ignored(
    monkeypatch,
    reset_message_dedup,
):
    import app

    send_calls = []
    monkeypatch.setattr(app, "ZALO_WEBHOOK_VERIFY_SIGNATURE", False)
    monkeypatch.setattr(
        app,
        "send_zalo_text",
        lambda **kwargs: send_calls.append(kwargs) or True,
    )
    client = app.app.test_client()
    response = client.post("/webhook", json={
        "event_name": "user_send_text",
        "sender": {"id": "user-01"},
        "message": {"text": "menu"},
    })

    assert response.get_json()["message"] == "Missing webhook identity"
    assert send_calls == []


def test_webhook_invalid_signature_and_oa_echo_are_ignored(
    monkeypatch,
    reset_message_dedup,
):
    import app

    send_calls = []
    monkeypatch.setattr(app, "ZALO_WEBHOOK_VERIFY_SIGNATURE", True)
    monkeypatch.setattr(app, "ZALO_APP_ID", "app-01")
    monkeypatch.setattr(app, "ZALO_OA_SECRET_KEY", "oa-secret")
    monkeypatch.setattr(
        app,
        "send_zalo_text",
        lambda **kwargs: send_calls.append(kwargs) or True,
    )
    client = app.app.test_client()

    invalid = client.post("/webhook", json={
        "app_id": "app-01",
        "timestamp": "1784192400000",
        "event_name": "user_send_text",
        "sender": {"id": "user-01"},
        "message": {"msg_id": "security-01", "text": "menu"},
    })
    echo = client.post("/webhook", json={
        "event_name": "oa_send_text",
        "sender": {"id": "oa-01"},
        "message": {"msg_id": "echo-01", "text": "Kết quả"},
    })

    assert invalid.get_json()["message"] == "Invalid webhook signature"
    assert echo.get_json()["message"] == "Event ignored"
    assert send_calls == []


def test_webhook_valid_signature_is_processed(
    monkeypatch,
    reset_message_dedup,
):
    import app

    payload = {
        "app_id": "app-01",
        "timestamp": "1784192400000",
        "event_name": "user_send_text",
        "sender": {"id": "user-01"},
        "message": {"msg_id": "security-02", "text": "menu"},
    }
    raw_body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    secret = "oa-secret"
    signature = hashlib.sha256(
        (
            payload["app_id"]
            + raw_body
            + payload["timestamp"]
            + secret
        ).encode("utf-8")
    ).hexdigest()
    send_calls = []

    monkeypatch.setattr(app, "ZALO_WEBHOOK_VERIFY_SIGNATURE", True)
    monkeypatch.setattr(app, "ZALO_APP_ID", "app-01")
    monkeypatch.setattr(app, "ZALO_OA_SECRET_KEY", secret)
    monkeypatch.setattr(
        app,
        "register_webhook_event",
        lambda **kwargs: "NEW",
    )
    monkeypatch.setattr(
        app,
        "build_answer",
        lambda **kwargs: ("Kết quả", "TEST"),
    )
    monkeypatch.setattr(
        app,
        "send_zalo_text",
        lambda **kwargs: send_calls.append(kwargs) or True,
    )
    client = app.app.test_client()
    response = client.post(
        "/webhook",
        data=raw_body,
        content_type="application/json",
        headers={"X-ZEvent-Signature": signature},
    )

    assert response.get_json()["success"] is True
    assert len(send_calls) == 1


def test_webhook_dedup_error_fails_closed(
    monkeypatch,
    reset_message_dedup,
):
    import app

    build_calls = []
    send_calls = []
    monkeypatch.setattr(app, "ZALO_WEBHOOK_VERIFY_SIGNATURE", False)
    monkeypatch.setattr(app, "WEBHOOK_DEDUP_FAIL_CLOSED", True)
    monkeypatch.setattr(
        app,
        "register_webhook_event",
        lambda **kwargs: "ERROR",
    )
    monkeypatch.setattr(
        app,
        "build_answer",
        lambda **kwargs: build_calls.append(kwargs) or ("Kết quả", "TEST"),
    )
    monkeypatch.setattr(
        app,
        "send_zalo_text",
        lambda **kwargs: send_calls.append(kwargs) or True,
    )
    client = app.app.test_client()
    response = client.post("/webhook", json={
        "event_name": "user_send_text",
        "timestamp": "1784192400000",
        "sender": {"id": "user-01"},
        "message": {"msg_id": "dedup-error-01", "text": "menu"},
    })

    assert response.get_json()["message"] == "Webhook dedup unavailable"
    assert build_calls == []
    assert send_calls == []
