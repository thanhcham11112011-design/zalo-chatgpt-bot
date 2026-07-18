from services import survey_service


SURVEY = {
    "MA_KHAO_SAT": "KS_HAILONG_001",
    "TEN_KHAO_SAT": "Khảo sát mức độ hài lòng",
    "LOI_MO_DAU": "Kính mời Quý công dân tham gia khảo sát.",
    "LOI_CAM_ON": "Cảm ơn Quý công dân đã tham gia khảo sát.",
    "CHO_PHEP_GUI_LAI": "FALSE",
    "TRANG_THAI": "HOAT_DONG",
    "UU_TIEN": "1",
    "PHIEN_BAN_KHAO_SAT": "V1",
}

QUESTIONS = [
    {
        "MA_KHAO_SAT": "KS_HAILONG_001",
        "MA_CAU_HOI": "KS01",
        "THU_TU": "1",
        "NOI_DUNG": "Quý công dân đã sử dụng nội dung nào?",
        "LOAI_CAU_HOI": "MOT_LUA_CHON",
        "PHUONG_AN": "1|Tra cứu thủ tục;2|Tra cứu liên hệ",
        "BAT_BUOC": "TRUE",
        "GOI_Y_NHAP": "Vui lòng nhập 1 hoặc 2.",
        "TRANG_THAI": "HOAT_DONG",
    },
    {
        "MA_KHAO_SAT": "KS_HAILONG_001",
        "MA_CAU_HOI": "KS02",
        "THU_TU": "2",
        "NOI_DUNG": "Quý công dân có góp ý gì?",
        "LOAI_CAU_HOI": "VAN_BAN",
        "PHUONG_AN": "",
        "BAT_BUOC": "FALSE",
        "GOI_Y_NHAP": "Nhập nội dung hoặc 0 để bỏ qua.",
        "TRANG_THAI": "HOAT_DONG",
    },
]

SETTINGS = {
    "SURVEY_CANCEL_KEYWORDS": "hủy khảo sát;dừng khảo sát",
    "SURVEY_RESTART_KEYWORDS": "làm lại khảo sát;khảo sát lại",
    "SURVEY_SKIP_KEYWORDS": "0;bỏ qua",
    "SURVEY_NO_ACTIVE_MESSAGE": "Hiện chưa có khảo sát.",
    "SURVEY_ALREADY_SUBMITTED_MESSAGE": "Quý công dân đã hoàn thành khảo sát.",
    "SURVEY_INVALID_ANSWER_MESSAGE": "Câu trả lời chưa hợp lệ.",
    "SURVEY_REQUIRED_MESSAGE": "Câu hỏi này là bắt buộc.",
    "SURVEY_CANCEL_MESSAGE": "Đã hủy khảo sát.",
    "SURVEY_SAVE_ERROR_MESSAGE": "Chưa lưu được phiếu khảo sát.",
}


# Chức năng: Thiết lập nguồn khảo sát giả lập dùng chung cho các bài test.
# Vai trò: Ngăn test truy cập Google Sheets thật và giữ dữ liệu kiểm thử ổn định.
def _patch_survey_defaults(monkeypatch):
    monkeypatch.setattr(
        survey_service,
        "ensure_survey_sheets",
        lambda: {},
    )
    monkeypatch.setattr(
        survey_service,
        "read_surveys",
        lambda: [dict(SURVEY)],
    )
    monkeypatch.setattr(
        survey_service,
        "read_survey_questions",
        lambda: [dict(row) for row in QUESTIONS],
    )
    monkeypatch.setattr(
        survey_service,
        "read_setting_chat",
        lambda: dict(SETTINGS),
    )
    monkeypatch.setattr(
        survey_service,
        "has_completed_survey",
        lambda user_id, survey_id: False,
    )


# Chức năng: Kiểm tra bắt đầu khảo sát tạo context và câu hỏi đầu tiên.
# Vai trò: Bảo đảm tuyến KHAO_SAT mở đúng phiếu đang hoạt động.
def test_start_survey_opens_first_question(monkeypatch):
    _patch_survey_defaults(monkeypatch)

    result = survey_service.start_survey("user-01")

    assert result["source"] == "KHAO_SAT_START"
    assert result["context"]["context_type"] == "KHAO_SAT"
    assert result["context"]["survey_id"] == "KS_HAILONG_001"
    assert result["context"]["survey_question_index"] == 0
    assert result["context"]["survey_version"] == "V1"
    assert "Câu 1/2" in result["reply"]
    assert "1. Tra cứu thủ tục" in result["reply"]


# Chức năng: Kiểm tra đáp án hợp lệ chuyển sang câu hỏi tiếp theo.
# Vai trò: Bảo đảm BOT_SESSION lưu đúng mã và nội dung phương án đã chọn.
def test_valid_option_moves_to_next_question(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    context = survey_service.start_survey("user-02")["context"]

    result = survey_service.process_survey_message(
        "user-02",
        "1",
        context,
        message_id="message-ks01",
    )

    assert result["source"] == "KHAO_SAT_QUESTION"
    assert result["context"]["survey_question_index"] == 1
    assert result["context"]["survey_answers"]["KS01"] == {
        "value": "1",
        "label": "Tra cứu thủ tục",
        "message_id": "message-ks01",
    }
    assert "Câu 2/2" in result["reply"]


# Chức năng: Kiểm tra đáp án ngoài danh sách không làm thay đổi tiến độ.
# Vai trò: Ngăn dữ liệu sai được ghi vào kết quả khảo sát.
def test_invalid_option_keeps_current_question(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    context = survey_service.start_survey("user-03")["context"]

    result = survey_service.process_survey_message(
        "user-03",
        "9",
        context,
    )

    assert result["source"] == "KHAO_SAT_INVALID"
    assert result["context"]["survey_question_index"] == 0
    assert result["context"]["survey_answers"] == {}
    assert "Câu trả lời chưa hợp lệ" in result["reply"]


# Chức năng: Kiểm tra không cho bỏ qua câu hỏi bắt buộc.
# Vai trò: Áp dụng đúng cột BAT_BUOC của CAU_HOI_KHAO_SAT.
def test_required_question_cannot_be_skipped(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    context = survey_service.start_survey("user-04")["context"]

    result = survey_service.process_survey_message(
        "user-04",
        "0",
        context,
    )

    assert result["source"] == "KHAO_SAT_REQUIRED"
    assert result["context"]["survey_question_index"] == 0
    assert "bắt buộc" in result["reply"]


# Chức năng: Kiểm tra câu không bắt buộc có thể bỏ qua và hoàn thành phiếu.
# Vai trò: Lưu một dòng đáp án rỗng nhưng vẫn giữ đủ cấu trúc câu hỏi trong kết quả.
def test_optional_question_can_be_skipped(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    saved = []
    monkeypatch.setattr(
        survey_service,
        "save_survey_results",
        lambda rows: saved.extend(rows) or True,
    )
    context = survey_service.start_survey("user-05")["context"]
    context = survey_service.process_survey_message(
        "user-05",
        "2",
        context,
    )["context"]

    result = survey_service.process_survey_message(
        "user-05",
        "0",
        context,
    )

    assert result["source"] == "KHAO_SAT_COMPLETE"
    assert result["context"] == {}
    assert len(saved) == 2
    assert saved[1]["MA_CAU_HOI"] == "KS02"
    assert saved[1]["CAU_TRA_LOI"] == ""


# Chức năng: Kiểm tra lệnh hủy kết thúc phiên khảo sát.
# Vai trò: Trả context rỗng để app.py xóa BOT_SESSION.
def test_cancel_survey_returns_empty_context(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    context = survey_service.start_survey("user-06")["context"]

    result = survey_service.process_survey_message(
        "user-06",
        "hủy khảo sát",
        context,
    )

    assert result["source"] == "KHAO_SAT_CANCEL"
    assert result["context"] == {}


# Chức năng: Kiểm tra lệnh làm lại tạo phiếu và mã biên nhận mới.
# Vai trò: Xóa đáp án tạm mà không coi người dùng đã gửi lại một phiếu hoàn thành.
def test_restart_survey_resets_answers(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    context = survey_service.start_survey("user-07")["context"]
    old_receipt = context["survey_receipt_id"]
    context = survey_service.process_survey_message(
        "user-07",
        "1",
        context,
    )["context"]

    result = survey_service.process_survey_message(
        "user-07",
        "làm lại khảo sát",
        context,
    )

    assert result["source"] == "KHAO_SAT_START"
    assert result["context"]["survey_question_index"] == 0
    assert result["context"]["survey_answers"] == {}
    assert result["context"]["survey_receipt_id"] != old_receipt


# Chức năng: Kiểm tra hoàn thành khảo sát ghi toàn bộ câu trả lời theo lô.
# Vai trò: Bảo đảm các dòng có cùng MA_PHIEU, USER_ID và trạng thái hoàn thành.
def test_complete_survey_writes_batch_rows(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    saved = []
    monkeypatch.setattr(
        survey_service,
        "save_survey_results",
        lambda rows: saved.append(rows) or True,
    )
    context = survey_service.start_survey("user-08")["context"]
    context = survey_service.process_survey_message(
        "user-08",
        "Tra cứu liên hệ",
        context,
        message_id="message-complete-01",
    )["context"]

    result = survey_service.process_survey_message(
        "user-08",
        "BOT cần phản hồi nhanh hơn",
        context,
        message_id="message-complete-02",
    )

    assert result["source"] == "KHAO_SAT_COMPLETE"
    assert len(saved) == 1
    assert len(saved[0]) == 2
    assert len({row["MA_PHIEU"] for row in saved[0]}) == 1
    assert all(row["USER_ID"] == "user-08" for row in saved[0])
    assert saved[0][0]["PHIEN_BAN_KHAO_SAT"] == "V1"
    assert saved[0][0]["MESSAGE_ID"] == "message-complete-01"
    assert saved[0][1]["MESSAGE_ID"] == "message-complete-02"
    assert saved[0][1]["NOI_DUNG_TRA_LOI"] == "BOT cần phản hồi nhanh hơn"
    assert len({row["HASH_PHIEU"] for row in saved[0]}) == 1
    assert len(saved[0][0]["HASH_PHIEU"]) == 64


# Chức năng: Kiểm tra người đã hoàn thành không được gửi lại khi cấu hình không cho phép.
# Vai trò: Thực hiện kiểm soát trùng dựa trên KET_QUA_KHAO_SAT.
def test_duplicate_submission_is_blocked(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    monkeypatch.setattr(
        survey_service,
        "has_completed_survey",
        lambda user_id, survey_id: True,
    )

    result = survey_service.start_survey("user-09")

    assert result["source"] == "KHAO_SAT_ALREADY_SUBMITTED"
    assert result["context"] == {}


# Chức năng: Kiểm tra không có khảo sát hoạt động trả thông báo từ SETTING_CHAT.
# Vai trò: Không tự suy luận hoặc mở phiếu đã hết hiệu lực.
def test_no_active_survey_returns_configured_message(monkeypatch):
    _patch_survey_defaults(monkeypatch)
    monkeypatch.setattr(
        survey_service,
        "read_surveys",
        lambda: [],
    )

    result = survey_service.start_survey("user-10")

    assert result["source"] == "KHAO_SAT_NO_ACTIVE"
    assert result["reply"] == "Hiện chưa có khảo sát."


# Chức năng: Kiểm tra Router trả tuyến KHAO_SAT khi MENU trỏ tới sheet khảo sát.
# Vai trò: Bảo đảm cách hỏi và số thứ tự khảo sát vẫn do MENU quyết định.
def test_router_returns_survey_route(monkeypatch):
    from services import router_service

    menu_row = {
        "ID": "12",
        "TEN_CHUC_NANG": "Khảo sát mức độ hài lòng",
        "SHEET_DU_LIEU": "KHAO_SAT",
        "MA_KHAO_SAT": "KS_HAILONG_001",
        "TRANG_THAI": "HOAT_DONG",
    }
    monkeypatch.setattr(
        router_service,
        "detect_bad_language",
        lambda text: None,
    )
    monkeypatch.setattr(
        router_service,
        "_match_survey_menu",
        lambda text: menu_row,
    )

    reply, source, context, ai_context = router_service.route_message(
        "khảo sát mức độ hài lòng"
    )

    assert reply == ""
    assert source == "KHAO_SAT"
    assert context["survey_id"] == "KS_HAILONG_001"
    assert context["last_route"] == "KHAO_SAT"
    assert ai_context == ""


# Chức năng: Kiểm tra app.py ưu tiên xử lý đáp án khi BOT_SESSION đang ở chế độ khảo sát.
# Vai trò: Ngăn đáp án số bị chuyển nhầm sang MENU hoặc thủ tục thông thường.
def test_app_build_answer_uses_active_survey_context(monkeypatch):
    import app

    active_context = {
        "context_type": "KHAO_SAT",
        "survey_id": "KS_HAILONG_001",
        "survey_question_index": 0,
    }
    cleared = []
    monkeypatch.setattr(app, "get_context", lambda user_id: active_context)
    monkeypatch.setattr(app, "is_survey_context", lambda context: True)
    monkeypatch.setattr(
        app,
        "route_message_for_ai",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Không được gọi Router thường")
        ),
    )
    monkeypatch.setattr(
        app,
        "process_survey_message",
        lambda **kwargs: {
            "reply": "Cảm ơn Quý công dân đã tham gia khảo sát.",
            "source": "KHAO_SAT_COMPLETE",
            "use_ai": False,
            "context": {},
            "ai_context": "",
            "ai_context_type": "",
            "ai_context_length": 0,
            "unknown_log": False,
        },
    )
    monkeypatch.setattr(
        app,
        "clear_context",
        lambda user_id: cleared.append(user_id) or True,
    )
    monkeypatch.setattr(app, "save_context", lambda *args, **kwargs: True)
    monkeypatch.setattr(app, "write_log_safe", lambda **kwargs: True)
    monkeypatch.setattr(app, "log_unknown_safe", lambda **kwargs: True)
    monkeypatch.setattr(app, "debug_log", lambda *args, **kwargs: None)

    answer, source = app.build_answer(
        "user-survey-app",
        "1",
        request_id="message-survey-01",
    )

    assert source == "KHAO_SAT_COMPLETE"
    assert "Cảm ơn" in answer
    assert cleared == ["user-survey-app"]


# Chức năng: Kiểm tra từ khóa và số MENU nhận đúng dòng khảo sát từ dữ liệu.
# Vai trò: Xác nhận Router không cần hardcode số 12 hoặc cụm từ khảo sát.
def test_match_survey_menu_uses_menu_data(monkeypatch):
    from services import router_service

    menu_row = {
        "ID": "12",
        "TEN_CHUC_NANG": "Khảo sát mức độ hài lòng",
        "TU_KHOA": "khảo sát;đánh giá bot",
        "SHEET_DU_LIEU": "KHAO_SAT",
        "TRANG_THAI": "HOAT_DONG",
    }
    monkeypatch.setattr(
        router_service,
        "read_menu",
        lambda: [menu_row],
    )
    monkeypatch.setattr(
        router_service,
        "search_menu",
        lambda text: menu_row if str(text).strip() == "12" else None,
    )

    assert router_service._match_survey_menu("khảo sát") == menu_row
    assert router_service._match_survey_menu("12") == menu_row


# Chức năng: Kiểm tra kết quả khảo sát được append nhiều dòng trong một lần ghi.
# Vai trò: Bảo đảm giảm lượt gọi Google Sheets API khi hoàn thành phiếu.
def test_save_survey_results_uses_batch_append(monkeypatch):
    from services import sheet_api

    appended = []

    class FakeWorksheet:
        # Chức năng: Ghi nhận dữ liệu append_rows của bài test.
        # Vai trò: Xác nhận một phiếu chỉ phát sinh một lần gọi ghi theo lô.
        def append_rows(self, values, value_input_option=None):
            appended.append((values, value_input_option))

    monkeypatch.setattr(
        sheet_api,
        "ensure_worksheet",
        lambda *args, **kwargs: FakeWorksheet(),
    )
    monkeypatch.setattr(
        sheet_api,
        "read_sheet",
        lambda *args, **kwargs: [],
    )
    sheet_api._cache.pop(sheet_api.SHEET_SURVEY_RESULTS, None)
    rows = [
        {
            "MA_PHIEU": "KS-001",
            "THOI_GIAN": "2026-07-19 08:00:00",
            "USER_ID": "user-01",
            "MA_KHAO_SAT": "KS_HAILONG_001",
            "MA_CAU_HOI": "KS01",
            "CAU_TRA_LOI": "1",
            "NOI_DUNG_TRA_LOI": "Rất hài lòng",
            "KENH_THUC_HIEN": "ZALO_OA",
            "TRANG_THAI": "HOAN_THANH",
            "PHIEN_BAN_KHAO_SAT": "V1",
            "MESSAGE_ID": "message-01",
            "HASH_PHIEU": "hash-01",
        },
        {
            "MA_PHIEU": "KS-001",
            "THOI_GIAN": "2026-07-19 08:00:00",
            "USER_ID": "user-01",
            "MA_KHAO_SAT": "KS_HAILONG_001",
            "MA_CAU_HOI": "KS02",
            "CAU_TRA_LOI": "Nhanh",
            "NOI_DUNG_TRA_LOI": "Nhanh",
            "KENH_THUC_HIEN": "ZALO_OA",
            "TRANG_THAI": "HOAN_THANH",
            "PHIEN_BAN_KHAO_SAT": "V1",
            "MESSAGE_ID": "message-02",
            "HASH_PHIEU": "hash-01",
        },
    ]

    result = sheet_api.save_survey_results(rows)

    assert result is True
    assert len(appended) == 1
    assert len(appended[0][0]) == 2
    assert appended[0][1] == "USER_ENTERED"


# Chức năng: Kiểm tra thay đổi đáp án khảo sát được đồng bộ vào BOT_SESSION.
# Vai trò: Bảo đảm tiến độ được phục hồi sau khi Render khởi động lại.
def test_survey_answer_change_persists_session(monkeypatch, reset_session_memory):
    from services import session_manager

    saved = []
    monkeypatch.setattr(
        session_manager,
        "save_session",
        lambda **kwargs: saved.append(kwargs) or True,
    )
    context = {
        "context_type": "KHAO_SAT",
        "survey_id": "KS_HAILONG_001",
        "survey_question_index": 0,
        "survey_answers": {},
    }
    session_manager.save_context("user-session-survey", context)
    context["survey_question_index"] = 1
    context["survey_answers"] = {
        "KS01": {"value": "1", "label": "Rất hài lòng"}
    }
    session_manager.save_context("user-session-survey", context)

    assert len(saved) == 2
    assert saved[-1]["context"]["survey_question_index"] == 1
    assert "KS01" in saved[-1]["context"]["survey_answers"]
