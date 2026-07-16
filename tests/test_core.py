from services import router_service
from services import search_engine
from services import sheet_api

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
    assert session_manager._memory["user-03"] == {}
    assert deleted_rows == [2]

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
    monkeypatch.setattr(
        router_service,
        "format_thu_tuc",
        lambda row: (
            f"📌 {row.get('TEN_THU_TUC', '')}\n\n"
            f"{row.get('HO_SO', '')}"
        ).strip(),
    )
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
            "MA_THU_TUC": "CCCD001",
            "TEN_THU_TUC": "Cấp căn cước cho người đủ 14 tuổi",
            "TU_KHOA": (
                "đủ 14 tuổi; làm căn cước đủ 14 tuổi; "
                "cấp căn cước cho người đủ 14 tuổi"
            ),
            "HO_SO": "Phiếu thu nhận thông tin và giấy tờ theo quy định.",
        },
        {
            "_SHEET": "THU_TUC_CCCD",
            "MA_THU_TUC": "CCCD_DUOI_14",
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
    assert context["procedure_id"] == "CCCD001"
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
        "procedure_id": "CCCD001",
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
        "MA_THU_TUC": "CUTRU005",
        "TEN_THU_TUC": "Đăng ký tạm trú",
        "HO_SO": "Tờ khai CT01 và giấy tờ chứng minh chỗ ở hợp pháp.",
        "LE_PHI": "Theo quy định hiện hành.",
        "DIEU_KIEN": "Có nơi tạm trú hợp pháp.",
    }
    context = {
        "sheet": "THU_TUC_CU_TRU",
        "topic": "Cư trú",
        "procedure_id": "CUTRU005",
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
        assert new_context["procedure_id"] == "CUTRU005"
        assert expected_title in reply
        assert expected_value in reply


# Chức năng: Kiểm tra thủ tục mới được ưu tiên hơn ngữ cảnh thủ tục cũ.
# Vai trò: Ngăn context cũ khóa chặt khi người dân nêu rõ thủ tục khác.
def test_regression_thu_tuc_moi_ghi_de_context_cu(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)

    procedures = [
        {
            "_SHEET": "THU_TUC_CU_TRU",
            "MA_THU_TUC": "CT_GIA_HAN_TAM_TRU",
            "TEN_THU_TUC": "Gia hạn tạm trú",
            "TU_KHOA": "gia hạn tạm trú",
            "HO_SO": "Hồ sơ gia hạn tạm trú.",
        },
        {
            "_SHEET": "THU_TUC_CU_TRU",
            "MA_THU_TUC": "CT_THUONG_TRU",
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
                if row["MA_THU_TUC"] == procedure_id
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

# Chức năng: Kiểm tra câu hỏi CCCD đủ 14 tuổi ghi đè context đăng ký xe tạm thời.
# Vai trò: Ngăn dữ liệu PTGT cũ được đưa sang Gemini khi người dân đổi thủ tục.
def test_regression_cccd_du_14_ghi_de_context_ptgt(
    monkeypatch,
):
    _patch_router_regression_defaults(monkeypatch)

    procedures = [
        {
            "_SHEET": "THU_TUC_CCCD",
            "MA_THU_TUC": "CCCD001",
            "TEN_THU_TUC": (
                "Cấp căn cước cho người từ đủ 14 tuổi trở lên"
            ),
            "TU_KHOA": "cấp căn cước; làm căn cước",
            "HO_SO": "Giấy tờ cần thiết theo quy định.",
        },
        {
            "_SHEET": "THU_TUC_PTGT",
            "MA_THU_TUC": "PTGT_TAM_THOI",
            "TEN_THU_TUC": "Đăng ký xe tạm thời",
            "TU_KHOA": "đăng ký xe tạm thời",
            "HO_SO": "Hồ sơ đăng ký xe tạm thời.",
        },
    ]

    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet_names",
        lambda: [
            "THU_TUC_CCCD",
            "THU_TUC_PTGT",
        ],
    )
    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet",
        lambda sheet_name: [
            row
            for row in procedures
            if row["_SHEET"] == sheet_name
        ],
    )

    old_context = {
        "sheet": "THU_TUC_PTGT",
        "topic": "Phương tiện giao thông",
        "procedure_id": "PTGT_TAM_THOI",
        "procedure_name": "Đăng ký xe tạm thời",
        "stage": "procedure",
    }

    reply, source, context, _ = (
        router_service.route_message(
            (
                "Đủ 14 tuổi khi đi làm CCCD "
                "cần mang theo giấy tờ gì?"
            ),
            old_context,
        )
    )

    assert (
        source
        == "THU_TUC_TU_KHOA_OVERRIDE_CONTEXT"
    )
    assert context["procedure_id"] == "CCCD001"
    assert context["sheet"] == "THU_TUC_CCCD"
    assert "Đăng ký xe tạm thời" not in reply


# Chức năng: Kiểm tra yêu cầu đăng ký tạm trú ghi đè context đăng ký xe tạm thời.
# Vai trò: Ngăn cụm đăng ký tạm trú bị hiểu thành câu nối tiếp của thủ tục PTGT cũ.
def test_regression_tam_tru_ghi_de_context_xe_tam_thoi(
    monkeypatch,
):
    _patch_router_regression_defaults(monkeypatch)

    procedures = [
        {
            "_SHEET": "THU_TUC_CU_TRU",
            "MA_THU_TUC": "CUTRU005",
            "TEN_THU_TUC": "Đăng ký tạm trú",
            "TU_KHOA": "tạm trú",
            "HO_SO": "Tờ khai CT01.",
        },
        {
            "_SHEET": "THU_TUC_PTGT",
            "MA_THU_TUC": "PTGT_TAM_THOI",
            "TEN_THU_TUC": "Đăng ký xe tạm thời",
            "TU_KHOA": "đăng ký xe tạm thời",
            "HO_SO": "Hồ sơ đăng ký xe tạm thời.",
        },
    ]

    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet_names",
        lambda: [
            "THU_TUC_CU_TRU",
            "THU_TUC_PTGT",
        ],
    )
    monkeypatch.setattr(
        router_service,
        "read_thu_tuc_sheet",
        lambda sheet_name: [
            row
            for row in procedures
            if row["_SHEET"] == sheet_name
        ],
    )

    old_context = {
        "sheet": "THU_TUC_PTGT",
        "topic": "Phương tiện giao thông",
        "procedure_id": "PTGT_TAM_THOI",
        "procedure_name": "Đăng ký xe tạm thời",
        "stage": "procedure",
    }

    reply, source, context, _ = (
        router_service.route_message(
            (
                "Tôi muốn đăng ký tạm trú, "
                "hãy hướng dẫn đầy đủ cho tôi"
            ),
            old_context,
        )
    )

    assert (
        source
        == "THU_TUC_TU_KHOA_OVERRIDE_CONTEXT"
    )
    assert (
        context["procedure_id"]
        == "CUTRU005"
    )
    assert context["sheet"] == "THU_TUC_CU_TRU"
    assert "Đăng ký tạm trú" in reply
    assert "Đăng ký xe tạm thời" not in reply


# Chức năng: Tạo dòng FAQ_INFO_001 giả lập đúng cấu trúc Google Sheets đang vận hành.
# Vai trò: Dùng chung dữ liệu nguồn cho bốn mã hồi quy P6-FAQ mà không đọc Sheet thật.
def _p6_faq_info_row():
    return {
        "ID": "FAQ_INFO_001",
        "CHU_DE": "Thông tin Công an phường",
        "CAU_HOI": "Địa chỉ Công an phường ở đâu?",
        "CAC_CACH_HOI": (
            "địa chỉ Công an;trụ sở ở đâu;"
            "Công an phường ở đâu;đến Công an phường thế nào"
        ),
        "TRA_LOI": "Tra cứu thông tin Công an phường.",
        "TU_KHOA": (
            "địa chỉ,trụ sở,Công an phường ở đâu,đến Công an,"
            "thông tin liên hệ,liên hệ Công an,Công an phường"
        ),
        "NGU_CANH": "THONGTIN",
        "RELATED_ID": (
            "DIA_CHI_1,,GOOGLE_MAP_1,DIA_CHI_2,"
            "GOOGLE_MAP_2,HOTLINE"
        ),
        "MUC_UU_TIEN": "100",
        "TRANG_THAI": "ON",
    }


# Chức năng: Thiết lập FAQ và THONGTIN giả lập cho kiểm thử P6-FAQ-001.
# Vai trò: Cho router dùng search_faq thật nhưng không truy cập Google Sheets vận hành.
def _patch_p6_faq_thongtin(monkeypatch):
    faq_row = _p6_faq_info_row()
    thongtin = {
        "DIA_CHI_1": "Cơ sở 1: số 130 đường Quy Tức",
        "GOOGLE_MAP_1": "https://maps.example/co-so-1",
        "DIA_CHI_2": "Cơ sở 2: số 169 đường Quy Tức",
        "GOOGLE_MAP_2": "https://maps.example/co-so-2",
        "HOTLINE": "02253876018",
    }

    monkeypatch.setattr(search_engine, "read_faq", lambda: [faq_row])
    monkeypatch.setattr(
        router_service,
        "search_faq",
        search_engine.search_faq,
    )
    monkeypatch.setattr(
        router_service,
        "read_thongtin",
        lambda: thongtin,
    )
    return faq_row, thongtin


# Chức năng: Kiểm tra câu hỏi ngắn tìm đúng FAQ_INFO_001 và dữ liệu THONGTIN.
# Vai trò: P6-FAQ-RT-001 ngăn quy tắc câu chi tiết ngắn loại FAQ địa chỉ đơn vị.
def test_p6_faq_rt_001_cong_an_phuong_o_dau(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)
    _, thongtin = _patch_p6_faq_thongtin(monkeypatch)

    reply, source, _, _ = router_service.route_message(
        "công an phường ở đâu"
    )

    assert source == "FAQ_THONGTIN"
    assert thongtin["DIA_CHI_1"] in reply
    assert thongtin["DIA_CHI_2"] in reply
    assert thongtin["HOTLINE"] in reply


# Chức năng: Kiểm tra câu hỏi có tên Phù Liễn vẫn trả cùng nhóm THONGTIN.
# Vai trò: P6-FAQ-RT-002 bảo đảm hai cách hỏi địa chỉ đi chung một nguồn dữ liệu.
def test_p6_faq_rt_002_cong_an_phuong_phu_lien_o_dau(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)
    _, thongtin = _patch_p6_faq_thongtin(monkeypatch)

    reply, source, _, _ = router_service.route_message(
        "công an phường phù liễn ở đâu"
    )

    assert source == "FAQ_THONGTIN"
    assert thongtin["DIA_CHI_1"] in reply
    assert thongtin["DIA_CHI_2"] in reply
    assert thongtin["HOTLINE"] in reply


# Chức năng: Kiểm tra câu nộp ở đâu tiếp tục dùng nơi nộp của thủ tục hiện tại.
# Vai trò: P6-FAQ-RT-003 ngăn FAQ THONGTIN cướp câu hỏi nối tiếp của thủ tục.
def test_p6_faq_rt_003_nop_o_dau_giu_context_thu_tuc(monkeypatch):
    _patch_router_regression_defaults(monkeypatch)
    _patch_p6_faq_thongtin(monkeypatch)
    procedure = {
        "_SHEET": "THU_TUC_CU_TRU",
        "MA_THU_TUC": "CUTRU005",
        "TEN_THU_TUC": "Đăng ký tạm trú",
        "NOI_THUC_HIEN": "Công an cấp xã nơi công dân tạm trú",
    }
    context = {
        "sheet": "THU_TUC_CU_TRU",
        "topic": "Cư trú",
        "procedure_id": "CUTRU005",
        "procedure_name": "Đăng ký tạm trú",
        "stage": "procedure",
    }
    monkeypatch.setattr(
        router_service,
        "find_procedure_by_id",
        lambda procedure_id: procedure,
    )
    monkeypatch.setattr(
        router_service,
        "find_lien_he_by_ten_co_quan",
        lambda name: None,
    )

    reply, source, new_context, _ = router_service.route_message(
        "nộp ở đâu",
        context,
    )

    assert source == "PROCEDURE_CONTEXT"
    assert new_context["procedure_id"] == "CUTRU005"
    assert "Cơ quan/nơi tiếp nhận - Đăng ký tạm trú" in reply
    assert "Công an cấp xã nơi công dân tạm trú" in reply
    assert "130 đường Quy Tức" not in reply


# Chức năng: Kiểm tra dấu phẩy kép trong RELATED_ID không tạo giá trị rỗng.
# Vai trò: P6-FAQ-RT-004 bảo đảm chỉ ghép các khóa THONGTIN hợp lệ theo đúng thứ tự.
def test_p6_faq_rt_004_related_id_dau_phay_kep(monkeypatch):
    faq_row, thongtin = _patch_p6_faq_thongtin(monkeypatch)

    reply = router_service._reply_thongtin_from_faq(faq_row)

    assert reply.splitlines() == [
        thongtin["DIA_CHI_1"],
        thongtin["GOOGLE_MAP_1"],
        thongtin["DIA_CHI_2"],
        thongtin["GOOGLE_MAP_2"],
        thongtin["HOTLINE"],
    ]


# Chức năng: Tạo context cũ đồng thời trong RAM và cache đọc BOT_SESSION.
# Vai trò: Mô phỏng đúng trạng thái làm P4-002 phục hồi thủ tục sau lệnh reset.
def _patch_p6_stale_session_context(monkeypatch, user_id):
    old_context = {
        "sheet": "THU_TUC_CCCD",
        "topic": "Căn cước",
        "procedure_id": "CCCD002",
        "procedure_name": "Cấp lại thẻ căn cước",
        "stage": "procedure",
        "last_route": "THU_TUC_TU_KHOA_GLOBAL",
    }
    cache_row = {
        "USER_ID": user_id,
        "CONTEXT_JSON": session_manager._context_json(old_context),
        "LAST_ROUTE": "THU_TUC_TU_KHOA_GLOBAL",
        "LAST_SHEET": "THU_TUC_CCCD",
        "LAST_RECORD_ID": "CCCD002",
        "LAST_MENU": "Căn cước",
        "LAST_PROCEDURE": "Cấp lại thẻ căn cước",
        "PAGE": "1",
        "UPDATED_AT": "2026-07-16T00:18:25",
    }
    sheet_values = [
        [
            "USER_ID",
            "CONTEXT_JSON",
            "LAST_ROUTE",
            "LAST_SHEET",
            "LAST_RECORD_ID",
            "LAST_MENU",
            "LAST_PROCEDURE",
            "PAGE",
            "UPDATED_AT",
        ],
        [
            user_id,
            cache_row["CONTEXT_JSON"],
            cache_row["LAST_ROUTE"],
            cache_row["LAST_SHEET"],
            cache_row["LAST_RECORD_ID"],
            cache_row["LAST_MENU"],
            cache_row["LAST_PROCEDURE"],
            cache_row["PAGE"],
            cache_row["UPDATED_AT"],
        ],
    ]

    class FakeWorksheet:
        # Chức năng: Trả dữ liệu BOT_SESSION có context cũ của người dùng thử nghiệm.
        # Vai trò: Cho clear_context tìm đúng dòng cần xóa mà không gọi Google Sheets thật.
        def get_all_values(self):
            return sheet_values

        # Chức năng: Ghi nhận thao tác xóa dòng BOT_SESSION giả lập.
        # Vai trò: Mô phỏng Sheet đã xóa nhưng cache đọc vẫn còn nếu mã không xử lý.
        def delete_rows(self, row_index):
            return row_index == 2

    monkeypatch.setattr(
        session_manager,
        "ensure_session_sheet",
        lambda: FakeWorksheet(),
    )
    monkeypatch.setattr(
        sheet_api,
        "_cache",
        {
            sheet_api.SHEET_SESSION: (
                sheet_api.time.time(),
                [
                    cache_row,
                    {
                        "USER_ID": "user-khac",
                        "CONTEXT_JSON": "{}",
                    },
                ],
            )
        },
    )
    session_manager._memory[user_id] = dict(old_context)
    return old_context


# Chức năng: Kiểm tra reset xóa cả context RAM và cache đọc BOT_SESSION.
# Vai trò: P6-CTX-RT-001 ngăn get_context phục hồi dòng thủ tục vừa được xóa khỏi Sheet.
def test_p6_ctx_rt_001_reset_xoa_cache_bot_session(
    monkeypatch,
    reset_session_memory,
):
    user_id = "user-p6-ctx-001"
    _patch_p6_stale_session_context(monkeypatch, user_id)

    result = session_manager.clear_context(user_id)
    restored_context = session_manager.get_context(user_id)

    assert result is True
    assert restored_context == {}
    cached_rows = sheet_api._cache[sheet_api.SHEET_SESSION][1]
    assert all(row.get("USER_ID") != user_id for row in cached_rows)
    assert any(row.get("USER_ID") == "user-khac" for row in cached_rows)


# Chức năng: Kiểm tra câu hỏi hồ sơ sau reset không dùng lại thủ tục cấp lại căn cước.
# Vai trò: P6-CTX-RT-002 tái hiện đầy đủ câu 3 của P4-002 trên context đã kết thúc.
def test_p6_ctx_rt_002_ho_so_sau_reset_khong_dung_context_cu(
    monkeypatch,
    reset_session_memory,
):
    user_id = "user-p6-ctx-002"
    _patch_router_regression_defaults(monkeypatch)
    _patch_p6_stale_session_context(monkeypatch, user_id)
    procedure = {
        "_SHEET": "THU_TUC_CCCD",
        "MA_THU_TUC": "CCCD002",
        "TEN_THU_TUC": "Cấp lại thẻ căn cước",
        "HO_SO": "Phiếu CC01 và Phiếu DC02.",
    }
    monkeypatch.setattr(
        router_service,
        "find_procedure_by_id",
        lambda procedure_id: procedure,
    )

    session_manager.clear_context(user_id)
    context = session_manager.get_context(user_id)
    reply, source, _, _ = router_service.route_message(
        "Hồ sơ gồm những gì?",
        context,
    )

    assert source == "DEFAULT"
    assert "Cấp lại thẻ căn cước" not in reply
    assert "Phiếu CC01" not in reply
