from services import router_service
from services import session_manager
from services import zalo_service
from services.text_utils import normalize_text


# Chức năng: Kiểm tra chuẩn hóa chữ tiếng Việt, khoảng trắng và chữ hoa.
# Vai trò: Bảo đảm đầu vào định tuyến có định dạng thống nhất.
def test_normalize_text_vietnamese():
    value = normalize_text("  Đăng   ký TẠM TRÚ  ")

    assert value == "dang ky tam tru"


# Chức năng: Kiểm tra số điện thoại không mất số 0 đầu khi chuẩn hóa.
# Vai trò: Bảo vệ dữ liệu liên hệ trong quá trình so khớp.
def test_normalize_text_keeps_phone_zero():
    value = normalize_text("SĐT: 0912610064")

    assert "0912610064" in value


# Chức năng: Kiểm tra lệnh mở menu và lệnh kết thúc phiên.
# Vai trò: Bảo đảm lệnh kỹ thuật không phụ thuộc dữ liệu nghiệp vụ.
def test_router_technical_commands():
    assert router_service.is_greeting("MENU") is True
    assert router_service.is_reset_question("Cảm ơn") is True
    assert router_service.is_greeting("đăng ký tạm trú") is False


# Chức năng: Kiểm tra tin nhắn ngắn không bị chia thành nhiều phần.
# Vai trò: Giữ nguyên trải nghiệm gửi tin khi nội dung dưới giới hạn.
def test_split_message_keeps_short_text(monkeypatch):
    monkeypatch.setattr(
        zalo_service,
        "_get_message_length_limit",
        lambda: 100,
    )

    parts = zalo_service._split_message("Nội dung ngắn.")

    assert parts == ["Nội dung ngắn."]


# Chức năng: Kiểm tra tin nhắn dài được chia đủ nội dung và đúng giới hạn.
# Vai trò: Phát hiện lỗi mất hoặc lặp nội dung khi tầng Zalo chia tin.
def test_split_message_preserves_long_text(monkeypatch):
    monkeypatch.setattr(
        zalo_service,
        "_get_message_length_limit",
        lambda: 55,
    )
    message = (
        "Phần thứ nhất hướng dẫn hồ sơ đăng ký tạm trú.\n\n"
        "Phần thứ hai hướng dẫn trình tự thực hiện thủ tục.\n\n"
        "Phần thứ ba hướng dẫn thời hạn và nơi nộp hồ sơ."
    )

    parts = zalo_service._split_message(message)

    assert len(parts) > 1
    assert all(len(part) <= 55 for part in parts)
    assert " ".join(" ".join(parts).split()) == " ".join(message.split())


# Chức năng: Kiểm tra tầng gửi Zalo gửi tuần tự toàn bộ các phần đã chia.
# Vai trò: Ngăn BOT dừng giữa danh sách khi nội dung có nhiều tin nhắn.
def test_send_zalo_text_sends_all_parts(monkeypatch):
    sent_parts = []

    monkeypatch.setattr(
        zalo_service,
        "_split_message",
        lambda message: ["Phần 1", "Phần 2", "Phần 3"],
    )
    monkeypatch.setattr(
        zalo_service,
        "_send_text_part",
        lambda user_id, message: sent_parts.append(
            (user_id, message)
        ) or True,
    )

    result = zalo_service.send_zalo_text(
        "user-test",
        "Nội dung dài",
    )

    assert result is True
    assert sent_parts == [
        ("user-test", "Phần 1"),
        ("user-test", "Phần 2"),
        ("user-test", "Phần 3"),
    ]


# Chức năng: Kiểm tra message_id lặp lại bị chặn trong thời hạn TTL.
# Vai trò: Ngăn Zalo nhận hai câu trả lời cho cùng một webhook.
def test_remember_message_blocks_duplicate(
    monkeypatch,
    reset_message_dedup,
):
    import app

    times = iter([100.0, 101.0, 120.0])
    monkeypatch.setattr(
        app,
        "MESSAGE_DEDUP_TTL_SECONDS",
        10,
    )
    monkeypatch.setattr(
        app.time,
        "monotonic",
        lambda: next(times),
    )

    assert app.remember_message("msg-01") is False
    assert app.remember_message("msg-01") is True
    assert app.remember_message("msg-01") is False


# Chức năng: Kiểm tra bộ nhớ webhook chỉ giữ tối đa số lượng cấu hình.
# Vai trò: Ngăn danh sách chống trùng tăng không giới hạn.
def test_remember_message_limits_memory(
    monkeypatch,
    reset_message_dedup,
):
    import app

    times = iter([1.0, 2.0, 3.0, 4.0])
    monkeypatch.setattr(
        app,
        "MESSAGE_DEDUP_TTL_SECONDS",
        600,
    )
    monkeypatch.setattr(
        app,
        "MAX_PROCESSED_MESSAGES",
        3,
    )
    monkeypatch.setattr(
        app.time,
        "monotonic",
        lambda: next(times),
    )

    for message_id in ["m1", "m2", "m3", "m4"]:
        assert app.remember_message(message_id) is False

    assert list(app.processed_messages.keys()) == [
        "m2",
        "m3",
        "m4",
    ]


# Chức năng: Kiểm tra get_context ưu tiên dữ liệu đang có trong bộ nhớ.
# Vai trò: Ngăn bài test gọi BOT_SESSION hoặc Google Sheets thật.
def test_get_context_uses_memory(
    monkeypatch,
    reset_session_memory,
):
    session_manager._memory["user-01"] = {
        "sheet": "THU_TUC_CU_TRU",
        "procedure_id": "CT_TAM_TRU",
    }

    def fail_if_sheet_is_called(user_id):
        raise AssertionError("Không được đọc BOT_SESSION")

    monkeypatch.setattr(
        session_manager,
        "read_session",
        fail_if_sheet_is_called,
    )

    context = session_manager.get_context("user-01")

    assert context["sheet"] == "THU_TUC_CU_TRU"
    assert context["procedure_id"] == "CT_TAM_TRU"


# Chức năng: Kiểm tra save_context không ghi lại khi ngữ cảnh kỹ thuật không đổi.
# Vai trò: Giảm số lần ghi BOT_SESSION không cần thiết.
def test_save_context_only_persists_changes(
    monkeypatch,
    reset_session_memory,
):
    saved = []

    monkeypatch.setattr(
        session_manager,
        "save_session",
        lambda **kwargs: saved.append(kwargs) or True,
    )

    context = {
        "sheet": "THU_TUC_CU_TRU",
        "topic": "Cư trú",
        "procedure_id": "CT_TAM_TRU",
        "procedure_name": "Đăng ký tạm trú",
        "stage": "procedure_detail",
        "page": 1,
        "last_suggestions": [],
    }

    assert session_manager.save_context("user-02", context) is True
    assert session_manager.save_context("user-02", context) is True
    assert len(saved) == 1


# Chức năng: Kiểm tra clear_context xóa cả bộ nhớ và dòng BOT_SESSION.
# Vai trò: Ngăn session rỗng hoặc context cũ còn tồn tại sau reset.
def test_clear_context_deletes_sheet_row(
    monkeypatch,
    reset_session_memory,
):
    deleted_rows = []

    class FakeWorksheet:
        # Chức năng: Trả dữ liệu BOT_SESSION giả lập.
        # Vai trò: Cho clear_context tìm đúng dòng user cần xóa.
        def get_all_values(self):
            return [
                ["USER_ID", "CONTEXT_JSON", "UPDATED_AT"],
                ["user-03", "{}", "2026-07-14T23:00:00"],
            ]

        # Chức năng: Ghi nhận số dòng được yêu cầu xóa.
        # Vai trò: Xác nhận clear_context không ghi session rỗng.
        def delete_rows(self, row_index):
            deleted_rows.append(row_index)

    session_manager._memory["user-03"] = {
        "sheet": "THU_TUC_CU_TRU",
    }
    monkeypatch.setattr(
        session_manager,
        "ensure_session_sheet",
        lambda: FakeWorksheet(),
    )

    result = session_manager.clear_context("user-03")

    assert result is True
    assert "user-03" not in session_manager._memory
    assert deleted_rows == [2]
