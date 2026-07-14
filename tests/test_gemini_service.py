from types import SimpleNamespace

from services import gemini_service


class FakeApiError(Exception):
    # Chức năng: Tạo lỗi API giả có mã và thông điệp giống Gemini SDK.
    # Vai trò: Kiểm thử phân loại lỗi mà không gọi mạng thật.
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class ScriptedModels:
    # Chức năng: Lưu chuỗi kết quả giả cho từng lần gọi generate_content.
    # Vai trò: Mô phỏng thành công, timeout hoặc lỗi cấu hình theo thứ tự.
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    # Chức năng: Trả kết quả tiếp theo hoặc phát sinh lỗi đã cấu hình.
    # Vai trò: Đếm chính xác số lần Gemini được gọi trong cơ chế retry.
    def generate_content(self, **kwargs):
        self.calls += 1

        if not self.outcomes:
            raise AssertionError("Gemini bị gọi nhiều hơn dự kiến")

        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class ScriptedClient:
    # Chức năng: Tạo Gemini client giả chứa models.generate_content.
    # Vai trò: Thay thế hoàn toàn client thật trong unit test.
    def __init__(self, outcomes):
        self.models = ScriptedModels(outcomes)


# Chức năng: Gắn toàn bộ dependency giả vào Gemini Service.
# Vai trò: Bảo đảm bài test không đọc Sheet, không ngủ thật và không gọi Gemini.
def _install_ai_mocks(
    monkeypatch,
    settings,
    outcomes,
    sleep_calls=None,
):
    client = ScriptedClient(outcomes)
    delays = sleep_calls if sleep_calls is not None else []

    monkeypatch.setattr(
        gemini_service,
        "_read_ai_settings",
        lambda: dict(settings),
    )
    monkeypatch.setattr(
        gemini_service,
        "_get_ai_config",
        lambda current_settings=None: (
            "test-api-key",
            "gemini-test",
        ),
    )
    monkeypatch.setattr(
        gemini_service,
        "_get_client",
        lambda settings=None, runtime=None: client,
    )
    monkeypatch.setattr(
        gemini_service,
        "build_prompt",
        lambda question, context="": "PROMPT_TEST",
    )
    monkeypatch.setattr(
        gemini_service,
        "_fallback_reply",
        lambda status="AI_FALLBACK": f"FALLBACK:{status}",
    )
    monkeypatch.setattr(
        gemini_service,
        "console_log",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        gemini_service.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )

    return client


# Chức năng: Kiểm tra timeout nhỏ hơn mức Gemini cho phép được nâng lên 10 giây.
# Vai trò: Ngăn lỗi INVALID_ARGUMENT do deadline quá ngắn.
def test_runtime_config_enforces_minimum_timeout(ai_settings):
    settings = dict(ai_settings)
    settings["AI_TIMEOUT_SECONDS"] = "1"

    runtime = gemini_service._get_runtime_config(settings)

    assert runtime["timeout_seconds"] == 10
    assert runtime["max_retries"] == 1
    assert runtime["retry_delay_seconds"] == 1.0
    assert runtime["retry_enabled"] is True


# Chức năng: Kiểm tra STRICT_SHEET_ONLY chặn AI khi không có ai_context.
# Vai trò: Ngăn Gemini tự suy diễn nghiệp vụ ngoài Google Sheets.
def test_strict_sheet_only_blocks_empty_context(ai_settings):
    allowed, status = gemini_service._ai_allowed(
        context="",
        settings=ai_settings,
    )

    assert allowed is False
    assert status == "NO_SHEET_CONTEXT"


# Chức năng: Kiểm tra lỗi cấu hình deadline quá ngắn không bị coi là timeout.
# Vai trò: Ngăn retry sai đối với lỗi HTTP 400 INVALID_ARGUMENT.
def test_classify_short_deadline_as_config_error():
    error = FakeApiError(
        400,
        (
            "INVALID_ARGUMENT: Manually set deadline 1s is too short. "
            "Minimum allowed deadline is 10s."
        ),
    )

    assert gemini_service._classify_error(error) == "CONFIG_ERROR"
    assert (
        gemini_service._is_retryable_status("CONFIG_ERROR")
        is False
    )


# Chức năng: Kiểm tra lỗi 504 DEADLINE_EXCEEDED được nhận diện là timeout.
# Vai trò: Cho phép retry đúng với lỗi tạm thời của Gemini.
def test_classify_deadline_exceeded_as_timeout():
    error = FakeApiError(
        504,
        "DEADLINE_EXCEEDED: The request timed out.",
    )

    assert gemini_service._classify_error(error) == "TIMEOUT"
    assert gemini_service._is_retryable_status("TIMEOUT") is True


# Chức năng: Kiểm tra Gemini thành công ngay lần gọi đầu tiên.
# Vai trò: Bảo đảm không retry khi đã có nội dung hợp lệ.
def test_ai_success_first_attempt(
    monkeypatch,
    ai_settings,
    reset_gemini_state,
):
    client = _install_ai_mocks(
        monkeypatch,
        ai_settings,
        [SimpleNamespace(text="Câu trả lời hợp lệ")],
    )

    result = gemini_service.ask_gemini_status(
        "Câu hỏi",
        context="Dữ liệu Sheet",
    )

    assert result["ok"] is True
    assert result["text"] == "Câu trả lời hợp lệ"
    assert result["ai_status"] == "ONLINE"
    assert client.models.calls == 1


# Chức năng: Kiểm tra timeout lần đầu và thành công ở lần retry.
# Vai trò: Xác nhận số lần gọi và thời gian nghỉ đọc đúng SETTING_AI.
def test_ai_timeout_then_retry_success(
    monkeypatch,
    ai_settings,
    reset_gemini_state,
):
    sleep_calls = []
    client = _install_ai_mocks(
        monkeypatch,
        ai_settings,
        [
            FakeApiError(
                504,
                "DEADLINE_EXCEEDED: The request timed out.",
            ),
            SimpleNamespace(text="Thành công sau retry"),
        ],
        sleep_calls=sleep_calls,
    )

    result = gemini_service.ask_gemini_status(
        "Câu hỏi",
        context="Dữ liệu Sheet",
    )

    assert result["ok"] is True
    assert result["text"] == "Thành công sau retry"
    assert client.models.calls == 2
    assert sleep_calls == [1.0]


# Chức năng: Kiểm tra hai lần timeout dẫn đến fallback an toàn.
# Vai trò: Bảo đảm lỗi AI không phát tán traceback ra câu trả lời.
def test_ai_timeout_all_attempts_returns_fallback(
    monkeypatch,
    ai_settings,
    reset_gemini_state,
):
    timeout_error = FakeApiError(
        504,
        "DEADLINE_EXCEEDED: The request timed out.",
    )
    client = _install_ai_mocks(
        monkeypatch,
        ai_settings,
        [timeout_error, timeout_error],
    )

    result = gemini_service.ask_gemini_status(
        "Câu hỏi",
        context="Dữ liệu Sheet",
    )

    assert result["ok"] is False
    assert result["ai_status"] == "TIMEOUT"
    assert result["text"] == "FALLBACK:TIMEOUT"
    assert client.models.calls == 2


# Chức năng: Kiểm tra tắt retry chỉ cho phép một lần gọi Gemini.
# Vai trò: Bảo đảm AI_RETRY_ENABLED được áp dụng đúng.
def test_ai_retry_disabled_calls_once(
    monkeypatch,
    ai_settings,
    reset_gemini_state,
):
    settings = dict(ai_settings)
    settings["AI_RETRY_ENABLED"] = "FALSE"
    client = _install_ai_mocks(
        monkeypatch,
        settings,
        [
            FakeApiError(
                504,
                "DEADLINE_EXCEEDED: The request timed out.",
            ),
            SimpleNamespace(text="Không được gọi tới kết quả này"),
        ],
    )

    result = gemini_service.ask_gemini_status(
        "Câu hỏi",
        context="Dữ liệu Sheet",
    )

    assert result["ok"] is False
    assert result["ai_status"] == "TIMEOUT"
    assert client.models.calls == 1


# Chức năng: Kiểm tra lỗi cấu hình dừng ngay và không retry.
# Vai trò: Ngăn BOT lặp lại yêu cầu chắc chắn tiếp tục thất bại.
def test_ai_config_error_does_not_retry(
    monkeypatch,
    ai_settings,
    reset_gemini_state,
):
    client = _install_ai_mocks(
        monkeypatch,
        ai_settings,
        [
            FakeApiError(
                400,
                "INVALID_ARGUMENT: invalid model",
            ),
            SimpleNamespace(text="Không được gọi tới kết quả này"),
        ],
    )

    result = gemini_service.ask_gemini_status(
        "Câu hỏi",
        context="Dữ liệu Sheet",
    )

    assert result["ok"] is False
    assert result["ai_status"] == "CONFIG_ERROR"
    assert client.models.calls == 1
