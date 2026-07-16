from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Chức năng: Cung cấp bộ cấu hình AI giả lập dùng chung cho các bài test.
# Vai trò: Ngăn test đọc SETTING_AI thật từ Google Sheets.
@pytest.fixture
def ai_settings():
    return {
        "MODEL": "gemini-test",
        "AI_ENABLED": "TRUE",
        "AI_MODE": "OPTIONAL",
        "AI_IS_CORE": "FALSE",
        "AI_STATUS": "ONLINE",
        "STRICT_SHEET_ONLY": "TRUE",
        "ALLOW_AI_WITHOUT_SHEET_CONTEXT": "FALSE",
        "TEMPERATURE": "0.2",
        "TOP_P": "0.9",
        "TOP_K": "40",
        "MAX_OUTPUT_TOKEN": "2048",
        "AI_MAX_OUTPUT_CHARS": "1500",
        "AI_TIMEOUT_SECONDS": "15",
        "AI_MAX_RETRIES": "1",
        "AI_RETRY_DELAY_SECONDS": "1",
        "AI_RETRY_ENABLED": "TRUE",
    }


# Chức năng: Xóa trạng thái Gemini client trước và sau mỗi bài test AI.
# Vai trò: Bảo đảm các bài test không dùng lại client từ bài test trước.
@pytest.fixture
def reset_gemini_state():
    from services import gemini_service

    gemini_service._client = None
    gemini_service._client_signature = ()

    yield

    gemini_service._client = None
    gemini_service._client_signature = ()


# Chức năng: Xóa bộ nhớ chống webhook trùng trước và sau bài test.
# Vai trò: Bảo đảm mỗi bài test message_id chạy độc lập.
@pytest.fixture
def reset_message_dedup():
    import app

    app.processed_messages.clear()

    yield

    app.processed_messages.clear()


# Chức năng: Xóa bộ nhớ session trước và sau mỗi bài test context.
# Vai trò: Ngăn context của bài test trước ảnh hưởng bài test sau.
@pytest.fixture
def reset_session_memory():
    from services import session_manager

    session_manager._memory.clear()

    yield

    session_manager._memory.clear()
# Chức năng: Thiết lập nguồn dữ liệu giả lập chung cho các bài test hồi quy định tuyến.
# Vai trò: Bảo đảm test không đọc Google Sheets, Gemini hoặc dữ liệu vận hành thật.
def _patch_router_regression_defaults(monkeypatch):
    monkeypatch.setattr(router_service, "detect_bad_language", lambda text: None)
    monkeypatch.setattr(router_service, "read_menu", lambda: [])
    monkeypatch.setattr(router_service, "search_menu", lambda text: None)
    monkeypatch.setattr(router_service, "search_faq", lambda text, limit=3: [])
    monkeypatch.setattr(router_service, "search_lien_he", lambda text, limit=999: [])
    monkeypatch.setattr(router_service, "read_lien_he", lambda: [])
    monkeypatch.setattr(router_service, "detect_bo_phan_contact", lambda text: "")
    monkeypatch.setattr(router_service, "read_thu_tuc_sheet_names", lambda: [])
    monkeypatch.setattr(router_service, "read_thu_tuc_sheet", lambda sheet_name: [])
    monkeypatch.setattr(router_service, "read_setting_chat", lambda: {})
    monkeypatch.setattr(router_service, "read_thongtin", lambda: {})


# Chức năng: Định dạng danh sách tên cán bộ từ dữ liệu liên hệ giả lập.
# Vai trò: Giúp test xác nhận kết quả sau khi router lọc bộ phận và địa bàn.
def _format_contact_names(rows, formatter, limit=5):
    return "\n".join(row["HO_TEN"] for row in rows[:limit])


# Chức năng: Kiểm tra câu hỏi người đủ 14 tuổi nhận đúng thủ tục căn cước.
# Vai trò: Ngăn BOT nhầm sang thủ tục dưới 14 tuổi hoặc thủ tục căn cước khác.
def test_regression_cccd_du_14_tuoi_dung_thu_tuc(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    procedures = [
        {
            "_SHEET": "THU_TUC_CCCD",
            "ID": "CCCD_DU_14",
            "TEN_THU_TUC": "Cấp căn cước cho người đủ 14 tuổi",
            "TU_KHOA": (
                "đủ 14 tuổi; làm căn cước đủ 14 tuổi; "
                "cấp căn cước cho người đủ 14 tuổi"
            ),
            "HO_SO": "Phiếu thu nhận thông tin và giấy tờ theo quy định.",
        },
        {
            "_SHEET": "THU_TUC_CCCD",
            "ID": "CCCD_DUOI_14",
            "TEN_THU_TUC": "Cấp căn cước cho người dưới 14 tuổi",
            "TU_KHOA": (
                "dưới 14 tuổi; trẻ em dưới 14 tuổi; "
                "cấp căn cước cho người dưới 14 tuổi"
            ),
            "HO_SO": "Hồ sơ dành cho người dưới 14 tuổi.",
        },
    ]

    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet_names",
        lambda: ["THU_TUC_CCCD"],
    )
    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet",
        lambda sheet_name: procedures,
    )

    reply, source, context, _ = router_service.route_message(
        "Đủ 14 tuổi khi đi làm CCCD cần mang theo giấy tờ gì?"
    )

    assert source == "THU_TUC_TU_KHOA_GLOBAL"
    assert context["procedure_id"] == "CCCD_DU_14"
    assert context["sheet"] == "THU_TUC_CCCD"
    assert "Cấp căn cước cho người đủ 14 tuổi" in reply
    assert "Phiếu thu nhận thông tin" in reply
    assert "dưới 14 tuổi" not in reply


# Chức năng: Kiểm tra FAQ hỏi nhiều câu liên tiếp không bị context thủ tục cướp luồng.
# Vai trò: Bảo đảm người dân đổi sang FAQ thì ngữ cảnh thủ tục cũ được xóa.
def test_regression_faq_nhieu_cau_lien_tiep_thoat_context(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    faq_row = {
        "ID": "FAQ_CHAT_001",
        "CAU_HOI": "Tôi có thể hỏi nhiều câu liên tiếp không",
        "TRA_LOI": "Quý công dân có thể hỏi nhiều câu liên tiếp.",
        "NGU_CANH": "",
        "RELATED_ID": "",
    }

    monkeypatch.setattr(
        router_service,
        "search_faq",
        lambda text, limit=3: [faq_row],
    )
    monkeypatch.setattr(
        router_service,
        "format_faq",
        lambda row: row["TRA_LOI"],
    )
    monkeypatch.setattr(
        router_service,
        "format_multiple_results",
        lambda rows, formatter, limit=3: formatter(rows[0]),
    )

    old_context = {
        "sheet": "THU_TUC_CCCD",
        "topic": "Căn cước",
        "procedure_id": "CCCD_DU_14",
        "procedure_name": "Cấp căn cước cho người đủ 14 tuổi",
        "stage": "procedure",
    }

    reply, source, context, _ = router_service.route_message(
        "Tôi có thể hỏi nhiều câu liên tiếp không",
        old_context,
    )

    assert source == "FAQ"
    assert reply == "Quý công dân có thể hỏi nhiều câu liên tiếp."
    assert context["procedure_id"] == ""
    assert context["sheet"] == ""
    assert context["stage"] == ""


# Chức năng: Kiểm tra yêu cầu liên hệ PCTP đi thẳng vào dữ liệu liên hệ.
# Vai trò: Ngăn câu hỏi liên hệ PCTP bị định tuyến nhầm sang MENU phản ánh ANTT.
def test_regression_lien_he_pctp_khong_vao_menu_antt(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    contact_rows = [
        {
            "ID": "PCTP_01",
            "BO_PHAN": "PCTP",
            "HO_TEN": "Phan Văn Trường",
            "SO_DIEN_THOAI": "0936718520",
        }
    ]

    monkeypatch.setattr(
        router_service,
        "detect_bo_phan_contact",
        lambda text: "PCTP",
    )
    monkeypatch.setattr(
        router_service,
        "search_lien_he",
        lambda text, limit=999: contact_rows,
    )
    monkeypatch.setattr(
        router_service,
        "format_multiple_results",
        _format_contact_names,
    )

    reply, source, context, _ = router_service.route_message(
        "Tôi muốn liên hệ bộ phận PCTP"
    )

    assert source == "TRA_CUU_LIEN_HE"
    assert source != "MENU"
    assert context == {}
    assert "Phan Văn Trường" in reply


# Chức năng: Kiểm tra câu yêu cầu trình báo được chuyển đến bộ phận PCTP.
# Vai trò: Ngăn BOT trả nhầm cán bộ chỉ huy khi người dân cần trình báo.
def test_regression_trinh_bao_tra_dung_pctp(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    contact_rows = [
        {
            "ID": "PCTP_01",
            "BO_PHAN": "PCTP",
            "HO_TEN": "Phan Văn Trường",
            "SO_DIEN_THOAI": "0936718520",
        }
    ]

    monkeypatch.setattr(
        router_service,
        "detect_bo_phan_contact",
        lambda text: "PCTP",
    )
    monkeypatch.setattr(
        router_service,
        "read_setting_chat",
        lambda: {
            "CONTACT_GUIDE_PCTP": (
                "Quý công dân vui lòng liên hệ bộ phận PCTP."
            )
        },
    )
    monkeypatch.setattr(
        router_service,
        "search_lien_he",
        lambda text, limit=999: contact_rows,
    )
    monkeypatch.setattr(
        router_service,
        "format_multiple_results",
        _format_contact_names,
    )

    reply, source, context, _ = router_service.route_message(
        "Tôi muốn trình báo"
    )

    assert source == "TRA_CUU_LIEN_HE"
    assert context == {}
    assert "Phan Văn Trường" in reply
    assert "CHI_HUY" not in reply


# Chức năng: Kiểm tra tra cứu CSKV Lệ Tảo lọc đúng cán bộ theo địa bàn.
# Vai trò: Ngăn kết quả PCTP hoặc địa bàn khác xuất hiện trong câu trả lời.
def test_regression_cskv_le_tao_khong_tra_pctp(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    contact_rows = [
        {
            "ID": "CSKV_LE_TAO",
            "BO_PHAN": "CSKV",
            "TDP": "Lệ Tảo",
            "HO_TEN": "Cao Đăng Nam",
            "SO_DIEN_THOAI": "0900000001",
        },
        {
            "ID": "PCTP_02",
            "BO_PHAN": "PCTP",
            "TDP": "",
            "HO_TEN": "Dương Đức Đông",
            "SO_DIEN_THOAI": "0987681687",
        },
    ]

    monkeypatch.setattr(
        router_service,
        "detect_bo_phan_contact",
        lambda text: "CSKV",
    )
    monkeypatch.setattr(
        router_service,
        "search_lien_he",
        lambda text, limit=999: contact_rows,
    )
    monkeypatch.setattr(
        router_service,
        "format_multiple_results",
        _format_contact_names,
    )

    reply, source, context, _ = router_service.route_message(
        "Tôi muốn liên hệ đồng chí CSKV tổ Lệ Tảo"
    )

    assert source == "TRA_CUU_LIEN_HE"
    assert context == {}
    assert "Cao Đăng Nam" in reply
    assert "Dương Đức Đông" not in reply


# Chức năng: Kiểm tra các câu hỏi ngắn tiếp tục dùng đúng thủ tục hiện tại.
# Vai trò: Bảo vệ context khi người dân hỏi hồ sơ, lệ phí hoặc điều kiện.
def test_regression_followup_chi_tiet_giu_context(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    procedure = {
        "_SHEET": "THU_TUC_CU_TRU",
        "ID": "CT_TAM_TRU",
        "TEN_THU_TUC": "Đăng ký tạm trú",
        "HO_SO": "Tờ khai CT01 và giấy tờ chứng minh chỗ ở hợp pháp.",
        "LE_PHI": "Theo quy định hiện hành.",
        "DIEU_KIEN": "Có nơi tạm trú hợp pháp.",
    }
    context = {
        "sheet": "THU_TUC_CU_TRU",
        "topic": "Cư trú",
        "procedure_id": "CT_TAM_TRU",
        "procedure_name": "Đăng ký tạm trú",
        "stage": "procedure",
    }
    cases = [
        ("hồ sơ", "Hồ sơ - Đăng ký tạm trú", "Tờ khai CT01"),
        ("lệ phí", "Lệ phí - Đăng ký tạm trú", "Theo quy định hiện hành"),
        ("điều kiện", "Điều kiện - Đăng ký tạm trú", "Có nơi tạm trú hợp pháp"),
    ]

    monkeypatch.setattr(
        router_service,
        "find_procedure_by_id",
        lambda procedure_id: procedure,
    )

    for question, expected_title, expected_value in cases:
        reply, source, new_context, _ = router_service.route_message(
            question,
            dict(context),
        )

        assert source == "PROCEDURE_CONTEXT"
        assert new_context["procedure_id"] == "CT_TAM_TRU"
        assert expected_title in reply
        assert expected_value in reply


# Chức năng: Kiểm tra thủ tục mới được ưu tiên hơn ngữ cảnh thủ tục cũ.
# Vai trò: Ngăn context cũ khóa chặt khi người dân nêu rõ thủ tục khác.
def test_regression_thu_tuc_moi_ghi_de_context_cu(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    procedures = [
        {
            "_SHEET": "THU_TUC_CU_TRU",
            "ID": "CT_GIA_HAN_TAM_TRU",
            "TEN_THU_TUC": "Gia hạn tạm trú",
            "TU_KHOA": "gia hạn tạm trú",
            "HO_SO": "Hồ sơ gia hạn tạm trú.",
        },
        {
            "_SHEET": "THU_TUC_CU_TRU",
            "ID": "CT_THUONG_TRU",
            "TEN_THU_TUC": "Đăng ký thường trú",
            "TU_KHOA": "đăng ký thường trú; hồ sơ đăng ký thường trú",
            "HO_SO": "Tờ khai CT01 và giấy tờ về chỗ ở hợp pháp.",
        },
    ]

    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet_names",
        lambda: ["THU_TUC_CU_TRU"],
    )
    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet",
        lambda sheet_name: procedures,
    )
    monkeypatch.setattr(
        router_service,
        "find_procedure_by_id",
        lambda procedure_id: next(
            (
                row
                for row in procedures
                if row["ID"] == procedure_id
            ),
            None,
        ),
    )

    old_context = {
        "sheet": "THU_TUC_CU_TRU",
        "topic": "Cư trú",
        "procedure_id": "CT_GIA_HAN_TAM_TRU",
        "procedure_name": "Gia hạn tạm trú",
        "stage": "procedure",
    }

    reply, source, context, _ = router_service.route_message(
        "Hồ sơ đăng ký thường trú",
        old_context,
    )

    assert source == "THU_TUC_TU_KHOA_OVERRIDE_CONTEXT"
    assert context["procedure_id"] == "CT_THUONG_TRU"
    assert "Hồ sơ - Đăng ký thường trú" in reply
    assert "Tờ khai CT01" in reply
    assert "Hồ sơ gia hạn tạm trú" not in reply


# Chức năng: Kiểm tra địa bàn ngoài danh sách chỉ nhận hướng dẫn làm rõ.
# Vai trò: Ngăn BOT mở rộng kết quả sang cán bộ của tổ dân phố khác.
def test_regression_tdp_ngoai_danh_sach_khong_mo_rong(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    contact_rows = [
        {
            "ID": "TDP_LE_TAO",
            "BO_PHAN": "BO_MAY_TDP",
            "TDP": "Lệ Tảo",
            "HO_TEN": "Cán bộ Lệ Tảo",
        },
        {
            "ID": "TDP_QUY_TUC",
            "BO_PHAN": "BO_MAY_TDP",
            "TDP": "Quy Tức",
            "HO_TEN": "Cán bộ Quy Tức",
        },
    ]
    guide_message = (
        "Chưa có dữ liệu TDP Hòa Bình trong danh sách địa bàn phục vụ. "
        "Quý công dân vui lòng kiểm tra lại tên tổ dân phố."
    )

    monkeypatch.setattr(
        router_service,
        "detect_bo_phan_contact",
        lambda text: "BO_MAY_TDP",
    )
    monkeypatch.setattr(
        router_service,
        "read_setting_chat",
        lambda: {
            "CONTACT_GUIDE_BO_MAY_TDP": guide_message,
        },
    )
    monkeypatch.setattr(
        router_service,
        "search_lien_he",
        lambda text, limit=999: contact_rows,
    )
    monkeypatch.setattr(
        router_service,
        "format_multiple_results",
        _format_contact_names,
    )

    reply, source, context, _ = router_service.route_message(
        "Trưởng ban CTMT TDP Hòa Bình"
    )

    assert source == "CONTACT_GUIDE_BY_DEPARTMENT"
    assert context["contact_department"] == "BO_MAY_TDP"
    assert reply == guide_message
    assert "Cán bộ Lệ Tảo" not in reply
    assert "Cán bộ Quy Tức" not in reply
