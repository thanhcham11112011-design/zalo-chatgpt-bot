import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from services.console_logger import console_log
from services.logger import current_time
from services.sheet_api import (
    ensure_survey_sheets,
    has_completed_survey,
    read_setting_chat,
    read_survey_questions,
    read_surveys,
    save_survey_results,
)
from services.text_utils import get_first, normalize_text, safe_int, split_list


SURVEY_CONTEXT_TYPE = "KHAO_SAT"
SURVEY_SOURCE_PREFIX = "KHAO_SAT"


# Chức năng: Chuẩn hóa giá trị cấu hình thành boolean.
# Vai trò: Đọc các cờ khảo sát từ Google Sheets theo một quy tắc thống nhất.
def _as_bool(value: Any, default: bool = False) -> bool:
    text = normalize_text(value)
    if not text:
        return default
    return text in {
        "1",
        "true",
        "yes",
        "on",
        "enable",
        "enabled",
        "bat",
        "co",
        "hoat dong",
    }


# Chức năng: Lấy cấu hình hội thoại khảo sát từ SETTING_CHAT.
# Vai trò: Không để câu thông báo và lệnh điều khiển nằm cứng trong survey_service.py.
def _chat_setting(key: str, default: str = "") -> str:
    data = read_setting_chat() or {}
    return str(data.get(key) or default or "").strip()


# Chức năng: Tạo kết quả định tuyến thống nhất cho app.py.
# Vai trò: Cho luồng khảo sát dùng chung cơ chế session, log và gửi Zalo hiện có.
def _route_result(
    reply: str,
    source: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "reply": str(reply or "").strip(),
        "source": str(source or SURVEY_SOURCE_PREFIX).strip(),
        "use_ai": False,
        "context": dict(context or {}),
        "ai_context": "",
        "ai_context_type": "",
        "ai_context_length": 0,
        "ai_mode": "OPTIONAL",
        "unknown_log": False,
    }


# Chức năng: Kiểm tra context hiện tại có phải một phiếu khảo sát đang thực hiện hay không.
# Vai trò: Ưu tiên tiếp nhận đáp án khảo sát trước Router MENU và thủ tục thông thường.
def is_survey_context(context: Optional[Dict[str, Any]]) -> bool:
    ctx = dict(context or {})
    return (
        normalize_text(ctx.get("context_type"))
        == normalize_text(SURVEY_CONTEXT_TYPE)
        and bool(str(ctx.get("survey_id") or "").strip())
    )


# Chức năng: Lấy mã khảo sát từ một dòng cấu hình hoặc context định tuyến.
# Vai trò: Hỗ trợ nhiều tên cột tương thích mà không gắn mã khảo sát trong Python.
def _survey_id(row: Optional[Dict[str, Any]]) -> str:
    return str(
        get_first(
            row or {},
            "MA_KHAO_SAT",
            "MÃ_KHẢO_SÁT",
            "ID",
            "RELATED_ID",
            default="",
        )
        or ""
    ).strip()


# Chức năng: Lấy mã câu hỏi từ một dòng Google Sheets.
# Vai trò: Dùng mã ổn định để lưu đáp án và đối chiếu kết quả khảo sát.
def _question_id(row: Optional[Dict[str, Any]]) -> str:
    return str(
        get_first(
            row or {},
            "MA_CAU_HOI",
            "MÃ_CÂU_HỎI",
            "ID",
            default="",
        )
        or ""
    ).strip()


# Chức năng: Chọn cuộc khảo sát đang hoạt động theo mã hoặc mức ưu tiên.
# Vai trò: Toàn bộ quyết định khảo sát nào được mở đều dựa trên dữ liệu sheet KHAO_SAT.
def _find_active_survey(survey_id: str = "") -> Optional[Dict[str, Any]]:
    clean_id = str(survey_id or "").strip()
    rows = list(read_surveys() or [])

    if clean_id:
        for row in rows:
            if _survey_id(row) == clean_id:
                return dict(row)
        return None

    rows.sort(
        key=lambda row: (
            safe_int(
                get_first(row, "UU_TIEN", "ƯU_TIÊN", default=999),
                default=999,
            ),
            _survey_id(row),
        )
    )
    return dict(rows[0]) if rows else None


# Chức năng: Lấy danh sách câu hỏi của một khảo sát theo đúng thứ tự cấu hình.
# Vai trò: Cho phép thêm, bớt hoặc sắp xếp câu hỏi hoàn toàn trên Google Sheets.
def _survey_questions(survey_id: str) -> List[Dict[str, Any]]:
    clean_id = str(survey_id or "").strip()
    rows = [
        dict(row)
        for row in (read_survey_questions() or [])
        if _survey_id(row) == clean_id
    ]
    rows.sort(
        key=lambda row: (
            safe_int(
                get_first(row, "THU_TU", "THỨ_TỰ", default=999),
                default=999,
            ),
            _question_id(row),
        )
    )
    return rows


# Chức năng: Chuẩn hóa mã loại câu hỏi từ Google Sheets.
# Vai trò: Điều khiển cách hiển thị và kiểm tra đáp án mà không gắn nội dung câu hỏi trong code.
def _question_type(question: Dict[str, Any]) -> str:
    return normalize_text(
        get_first(
            question,
            "LOAI_CAU_HOI",
            "LOẠI_CÂU_HỎI",
            default="VAN_BAN",
        )
    ).replace(" ", "_").upper()


# Chức năng: Đọc trạng thái bắt buộc của một câu hỏi.
# Vai trò: Ngăn bỏ qua những câu được đơn vị đánh dấu bắt buộc trong Google Sheets.
def _is_required(question: Dict[str, Any]) -> bool:
    return _as_bool(
        get_first(
            question,
            "BAT_BUOC",
            "BẮT_BUỘC",
            default="FALSE",
        ),
        False,
    )


# Chức năng: Tách danh sách phương án thành cặp mã và nội dung hiển thị.
# Vai trò: Hỗ trợ cấu trúc 1|Nội dung;2|Nội dung và tự tạo mã khi sheet chỉ có nội dung.
def _parse_options(question: Dict[str, Any]) -> List[Tuple[str, str]]:
    raw = str(
        get_first(
            question,
            "PHUONG_AN",
            "PHƯƠNG_ÁN",
            default="",
        )
        or ""
    ).strip()
    parts = [
        item.strip()
        for item in re.split(r"[;\n]+", raw)
        if item and item.strip()
    ]
    options: List[Tuple[str, str]] = []

    for index, item in enumerate(parts, start=1):
        if "|" in item:
            key, label = item.split("|", 1)
        else:
            key, label = str(index), item

        clean_key = str(key or "").strip() or str(index)
        clean_label = str(label or "").strip()
        if clean_label:
            options.append((clean_key, clean_label))

    return options


# Chức năng: Định dạng một câu hỏi khảo sát thành tin nhắn Zalo.
# Vai trò: Hiển thị số thứ tự, phương án và gợi ý nhập từ dữ liệu Google Sheets.
def _format_question(
    question: Dict[str, Any],
    index: int,
    total: int,
) -> str:
    content = str(
        get_first(
            question,
            "NOI_DUNG",
            "NỘI_DUNG",
            "CAU_HOI",
            "CÂU_HỎI",
            default="",
        )
        or ""
    ).strip()
    hint = str(
        get_first(
            question,
            "GOI_Y_NHAP",
            "GỢI_Ý_NHẬP",
            default="",
        )
        or ""
    ).strip()
    lines = [f"Câu {index + 1}/{total}: {content}".strip()]

    for key, label in _parse_options(question):
        lines.append(f"{key}. {label}")

    if hint:
        lines.extend(["", hint])

    return "\n".join(line for line in lines if line is not None).strip()


# Chức năng: Kiểm tra tin nhắn có khớp một nhóm lệnh được cấu hình hay không.
# Vai trò: Quản lý hủy, làm lại và bỏ qua mà không hardcode từ khóa nghiệp vụ.
def _matches_command(text: str, setting_key: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False

    commands = split_list(_chat_setting(setting_key, ""))
    return any(
        normalized == normalize_text(command)
        for command in commands
        if normalize_text(command)
    )


# Chức năng: Kiểm tra và chuẩn hóa câu trả lời theo loại câu hỏi.
# Vai trò: Chỉ chấp nhận mã hoặc nội dung phương án hợp lệ và giữ nguyên ý kiến văn bản.
def _validate_answer(
    question: Dict[str, Any],
    user_text: str,
) -> Tuple[bool, str, str]:
    raw = str(user_text or "").strip()
    question_type = _question_type(question)
    options = _parse_options(question)

    if question_type in {
        "MOT_LUA_CHON",
        "DANH_GIA",
        "CO_KHONG",
        "SINGLE_CHOICE",
        "RATING",
        "YES_NO",
    } or options:
        normalized = normalize_text(raw)

        for key, label in options:
            if normalized in {
                normalize_text(key),
                normalize_text(label),
            }:
                return True, key, label

        return False, "", ""

    if not raw:
        return False, "", ""

    return True, raw, raw


# Chức năng: Tạo context mới khi bắt đầu hoặc làm lại một phiếu khảo sát.
# Vai trò: Lưu tiến độ kỹ thuật trong BOT_SESSION để người dùng có thể tiếp tục sau mỗi tin nhắn.
def _new_survey_context(
    survey: Dict[str, Any],
    total_questions: int,
) -> Dict[str, Any]:
    survey_id = _survey_id(survey)
    survey_name = str(
        get_first(
            survey,
            "TEN_KHAO_SAT",
            "TÊN_KHẢO_SÁT",
            default=survey_id,
        )
        or survey_id
    ).strip()
    return {
        "context_type": SURVEY_CONTEXT_TYPE,
        "sheet": "KHAO_SAT",
        "topic": survey_name,
        "stage": "survey_question",
        "procedure_id": "",
        "procedure_name": "",
        "page": 1,
        "last_suggestions": [],
        "last_route": "KHAO_SAT_START",
        "survey_id": survey_id,
        "survey_name": survey_name,
        "survey_question_index": 0,
        "survey_total_questions": total_questions,
        "survey_answers": {},
        "survey_receipt_id": f"KS-{uuid.uuid4().hex[:12].upper()}",
        "survey_started_at": datetime.now().isoformat(timespec="seconds"),
    }


# Chức năng: Mở cuộc khảo sát đang hoạt động và gửi câu hỏi đầu tiên.
# Vai trò: Chuyển tuyến KHAO_SAT từ Router thành một phiên khảo sát có trạng thái trong BOT_SESSION.
def start_survey(
    user_id: str,
    route_context: Optional[Dict[str, Any]] = None,
    force_restart: bool = False,
) -> Dict[str, Any]:
    try:
        ensure_survey_sheets()
        requested_id = str(
            get_first(
                route_context or {},
                "survey_id",
                "MA_KHAO_SAT",
                "RELATED_ID",
                default="",
            )
            or ""
        ).strip()
        survey = _find_active_survey(requested_id)

        if not survey:
            return _route_result(
                _chat_setting(
                    "SURVEY_NO_ACTIVE_MESSAGE",
                    "Hiện chưa có phiếu khảo sát đang hoạt động.",
                ),
                "KHAO_SAT_NO_ACTIVE",
                {},
            )

        survey_id = _survey_id(survey)
        allow_repeat = _as_bool(
            get_first(
                survey,
                "CHO_PHEP_GUI_LAI",
                "CHO_PHÉP_GỬI_LẠI",
                default="FALSE",
            ),
            False,
        )

        if (
            not force_restart
            and not allow_repeat
            and has_completed_survey(user_id, survey_id)
        ):
            return _route_result(
                _chat_setting(
                    "SURVEY_ALREADY_SUBMITTED_MESSAGE",
                    "Quý công dân đã hoàn thành phiếu khảo sát này.",
                ),
                "KHAO_SAT_ALREADY_SUBMITTED",
                {},
            )

        questions = _survey_questions(survey_id)
        if not questions:
            return _route_result(
                _chat_setting(
                    "SURVEY_NO_QUESTION_MESSAGE",
                    "Phiếu khảo sát chưa có câu hỏi hợp lệ.",
                ),
                "KHAO_SAT_ERROR",
                {},
            )

        context = _new_survey_context(survey, len(questions))
        introduction = str(
            get_first(
                survey,
                "LOI_MO_DAU",
                "LỜI_MỞ_ĐẦU",
                default="",
            )
            or ""
        ).strip()
        first_question = _format_question(
            questions[0],
            0,
            len(questions),
        )
        reply = "\n\n".join(
            part
            for part in [introduction, first_question]
            if str(part or "").strip()
        )
        return _route_result(
            reply,
            "KHAO_SAT_START",
            context,
        )

    except Exception as error:
        console_log(
            "ERROR",
            "SURVEY",
            "Khởi động khảo sát thất bại",
            user_id=user_id,
            error=error,
        )
        return _route_result(
            _chat_setting(
                "SURVEY_ERROR_MESSAGE",
                "Hệ thống khảo sát đang tạm thời bận. Quý công dân vui lòng thử lại sau.",
            ),
            "KHAO_SAT_ERROR",
            {},
        )


# Chức năng: Chuyển các đáp án trong context thành các dòng kết quả cùng một mã phiếu.
# Vai trò: Chuẩn bị dữ liệu ghi theo lô vào KET_QUA_KHAO_SAT khi người dùng hoàn thành.
def _result_rows(
    user_id: str,
    context: Dict[str, Any],
    questions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    answers = dict(context.get("survey_answers") or {})
    timestamp = current_time()
    rows: List[Dict[str, Any]] = []

    for question in questions:
        question_id = _question_id(question)
        answer = dict(answers.get(question_id) or {})
        rows.append({
            "MA_PHIEU": context.get("survey_receipt_id", ""),
            "THOI_GIAN": timestamp,
            "USER_ID": user_id,
            "MA_KHAO_SAT": context.get("survey_id", ""),
            "MA_CAU_HOI": question_id,
            "CAU_TRA_LOI": answer.get("value", ""),
            "NOI_DUNG_TRA_LOI": answer.get("label", ""),
            "KENH_THUC_HIEN": "ZALO_OA",
            "TRANG_THAI": "HOAN_THANH",
        })

    return rows


# Chức năng: Tiếp nhận một đáp án, cập nhật tiến độ hoặc hoàn thành phiếu khảo sát.
# Vai trò: Giữ toàn bộ hội thoại khảo sát trong luồng riêng trước khi quay lại Router thông thường.
def process_survey_message(
    user_id: str,
    user_text: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        ensure_survey_sheets()
        ctx = dict(context or {})
        survey_id = str(ctx.get("survey_id") or "").strip()
        survey = _find_active_survey(survey_id)

        if not survey:
            return _route_result(
                _chat_setting(
                    "SURVEY_NO_ACTIVE_MESSAGE",
                    "Phiếu khảo sát hiện không còn hoạt động.",
                ),
                "KHAO_SAT_NO_ACTIVE",
                {},
            )

        if _matches_command(user_text, "SURVEY_CANCEL_KEYWORDS"):
            return _route_result(
                _chat_setting(
                    "SURVEY_CANCEL_MESSAGE",
                    "Đã hủy phiếu khảo sát.",
                ),
                "KHAO_SAT_CANCEL",
                {},
            )

        if _matches_command(user_text, "SURVEY_RESTART_KEYWORDS"):
            return start_survey(
                user_id,
                {"survey_id": survey_id},
                force_restart=True,
            )

        questions = _survey_questions(survey_id)
        index = safe_int(
            ctx.get("survey_question_index"),
            default=0,
        )

        if not questions or index < 0 or index >= len(questions):
            return _route_result(
                _chat_setting(
                    "SURVEY_ERROR_MESSAGE",
                    "Không thể tiếp tục phiếu khảo sát hiện tại.",
                ),
                "KHAO_SAT_ERROR",
                {},
            )

        question = questions[index]
        skipped = _matches_command(
            user_text,
            "SURVEY_SKIP_KEYWORDS",
        )

        if skipped and _is_required(question):
            message = _chat_setting(
                "SURVEY_REQUIRED_MESSAGE",
                "Câu hỏi này là bắt buộc. Quý công dân vui lòng nhập câu trả lời.",
            )
            return _route_result(
                f"{message}\n\n{_format_question(question, index, len(questions))}",
                "KHAO_SAT_REQUIRED",
                ctx,
            )

        if skipped:
            valid, answer_value, answer_label = True, "", ""
        else:
            valid, answer_value, answer_label = _validate_answer(
                question,
                user_text,
            )

        if not valid:
            message = _chat_setting(
                "SURVEY_INVALID_ANSWER_MESSAGE",
                "Câu trả lời chưa hợp lệ. Quý công dân vui lòng chọn đúng phương án hoặc nhập lại nội dung.",
            )
            return _route_result(
                f"{message}\n\n{_format_question(question, index, len(questions))}",
                "KHAO_SAT_INVALID",
                ctx,
            )

        question_id = _question_id(question)
        answers = dict(ctx.get("survey_answers") or {})
        answers[question_id] = {
            "value": answer_value,
            "label": answer_label,
        }
        ctx["survey_answers"] = answers
        ctx["last_route"] = "KHAO_SAT_ANSWER"

        if index + 1 < len(questions):
            next_index = index + 1
            ctx["survey_question_index"] = next_index
            ctx["survey_total_questions"] = len(questions)
            return _route_result(
                _format_question(
                    questions[next_index],
                    next_index,
                    len(questions),
                ),
                "KHAO_SAT_QUESTION",
                ctx,
            )

        rows = _result_rows(
            user_id,
            ctx,
            questions,
        )
        if not save_survey_results(rows):
            ctx["last_route"] = "KHAO_SAT_SAVE_ERROR"
            return _route_result(
                _chat_setting(
                    "SURVEY_SAVE_ERROR_MESSAGE",
                    "Hệ thống chưa lưu được phiếu khảo sát. Quý công dân vui lòng gửi lại câu trả lời cuối cùng.",
                ),
                "KHAO_SAT_SAVE_ERROR",
                ctx,
            )

        thank_you = str(
            get_first(
                survey,
                "LOI_CAM_ON",
                "LỜI_CẢM_ƠN",
                default="",
            )
            or ""
        ).strip()
        if not thank_you:
            thank_you = _chat_setting(
                "SURVEY_THANK_YOU_MESSAGE",
                "Cảm ơn Quý công dân đã tham gia khảo sát.",
            )

        return _route_result(
            thank_you,
            "KHAO_SAT_COMPLETE",
            {},
        )

    except Exception as error:
        console_log(
            "ERROR",
            "SURVEY",
            "Xử lý câu trả lời khảo sát thất bại",
            user_id=user_id,
            error=error,
        )
        return _route_result(
            _chat_setting(
                "SURVEY_ERROR_MESSAGE",
                "Hệ thống khảo sát đang tạm thời bận. Quý công dân vui lòng thử lại sau.",
            ),
            "KHAO_SAT_ERROR",
            {},
        )
