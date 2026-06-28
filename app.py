from flask import Flask, request, jsonify
from flask_cors import CORS

from config import (
    HOST,
    PORT,
    BOT_NAME,
    MAX_HISTORY,
)

from services.sheet_api import sheet_api
from services.gemini_service import gemini_service
from services.zalo_service import zalo_service
from services import contact_service
from services import router_service

app = Flask(__name__)
CORS(app)

conversation_memory = {}
processed_messages = set()
user_states = {}

def remember(user_id, role, text):
    history = conversation_memory.get(user_id, [])

    history.append({
        "role": role,
        "text": text
    })

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    conversation_memory[user_id] = history


def get_history_text(user_id):
    history = conversation_memory.get(user_id, [])

    lines = []

    for item in history:
        lines.append(
            f"{item['role']}: {item['text']}"
        )

    return "\n".join(lines)


def build_sheet_answer(question, context_items):
    if not context_items:
        return None

    item = context_items[0]

    title = (
        item.get("TEN_THU_TUC")
        or item.get("CAU_HOI")
        or item.get("TIEU_DE")
        or item.get("TEN")
        or ""
    )

    short_answer = (
        item.get("TRA_LOI_NGAN")
        or item.get("TRA_LOI")
        or item.get("NOI_DUNG")
        or ""
    )

    full_answer = item.get("TRA_LOI_DAY_DU") or ""

    ho_so = item.get("HO_SO") or ""
    trinh_tu = item.get("TRINH_TU") or ""
    noi_nop = item.get("NOI_NOP") or ""
    thoi_han = item.get("THOI_HAN") or ""
    le_phi = item.get("LE_PHI") or ""
    link = item.get("LINK_DVC") or ""
    video_hd = item.get("VIDEO_HD") or ""
    source_sheet = item.get("_SOURCE_SHEET", "")

    parts = []

    if title:
        parts.append(f"📌 {title}")

    if short_answer:
        parts.append(short_answer)
    elif full_answer:
        parts.append(full_answer)

    if ho_so:
        parts.append(f"📄 Hồ sơ cần chuẩn bị:\n{ho_so}")

    if trinh_tu:
        parts.append(f"📝 Trình tự thực hiện:\n{trinh_tu}")

    if noi_nop:
        parts.append(f"📍 Nơi nộp:\n{noi_nop}")

    if thoi_han:
        parts.append(f"⏱ Thời hạn giải quyết:\n{thoi_han}")

    if le_phi:
        parts.append(f"💰 Lệ phí:\n{le_phi}")

    
    if source_sheet == "THU_TUC_VNEID":
        if video_hd:
            parts.append(f"🎥 Video hướng dẫn:\n{video_hd}")
    else:
        if link:
            parts.append(f"🔗 Link dịch vụ công:\n{link}")

    if not parts:
        return None

    return "\n\n".join(parts)

def build_menu_from_sheet():
    try:
        menu_rows = sheet_api.read_menu()

        if not menu_rows:
            return None

        lines = []

        for index, row in enumerate(menu_rows, start=1):
            title = (
                row.get("TEN")
                or row.get("TEN_CHUC_NANG")
                or row.get("Tên chức năng")
                or row.get("CHU_DE")
                or row.get("MO_TA")
                or ""
            )

            title = str(title).strip()

            if title:
                lines.append(f"{index}. {title}")

        if not lines:
            return None

        return "\n".join(lines)

    except Exception as e:
        print("BUILD MENU ERROR:", e)
        return None


def answer_greeting(question):
    q = str(question or "").lower().strip()

    greetings = [
        "xin chào",
        "chào",
        "chào bạn",
        "hello",
        "hi",
        "alo",
        "menu",
        "danh mục",
        "0"
    ]

    if q not in greetings:
        return None

    menu_text = build_menu_from_sheet()

    if not menu_text:
        menu_text = (
            "1. Căn cước\n"
            "2. Cư trú\n"
            "3. VNeID\n"
            "4. Phương tiện giao thông\n"
            "5. Ngành nghề đầu tư kinh doanh có điều kiện về ANTT\n"
            "6. Phòng cháy chữa cháy\n"
            "7. Vũ khí - Vật liệu nổ - Công cụ hỗ trợ\n"
            "8. Tra cứu liên hệ\n"
        )

    return (
        "🇻🇳 CHÀO MỪNG QUÝ CÔNG DÂN\n"
        "Đến với Trợ lý AI Công an phường Phù Liễn, thành phố Hải Phòng.\n\n"
        "🤖 Tôi có thể hỗ trợ tra cứu thủ tục hành chính, hướng dẫn hồ sơ, "
        "địa điểm tiếp nhận, thời hạn giải quyết và giải đáp câu hỏi thường gặp.\n\n"
        "📋 DANH MỤC HỖ TRỢ\n"
        f"{menu_text}\n\n"
        "💬 Quý công dân có thể nhập số thứ tự hoặc nhập trực tiếp nội dung cần hỏi.\n\n"
        "Ví dụ:\n"
        "• Cấp lại căn cước\n"
        "• Đăng ký thường trú\n"
        "• Kích hoạt VNeID mức 2\n"
        "• Đăng ký xe máy\n"
        "• Số điện thoại trực ban\n\n"
        "Xin mời Quý công dân nhập nội dung cần hỗ trợ."
    )
def build_procedure_list(sheet_name):
    rows = sheet_api.read_sheet(sheet_name)

    if not rows:
        return None

    lines = []

    for index, row in enumerate(rows, start=1):
        name = (
            row.get("TEN_THU_TUC")
            or row.get("Tên thủ tục")
            or row.get("TEN")
            or row.get("MO_TA")
            or ""
        )

        name = str(name).strip()

        if name:
            lines.append(f"{index}. {name}")

    if not lines:
        return None

    return (
    "📋 DANH SÁCH THỦ TỤC\n\n"
    + "\n".join(lines)
    + "\n\n"
    "📌 Quý công dân muốn tìm hiểu hoặc thực hiện thủ tục nào, "
    "xin vui lòng nhắn đúng tên thủ tục theo danh sách trên để được hướng dẫn chi tiết."
)
def set_user_state(user_id, state):
    user_states[user_id] = state


def get_user_state(user_id):
    return user_states.get(user_id)


def clear_user_state(user_id):
    if user_id in user_states:
        del user_states[user_id]


def build_procedure_detail(row):
    return build_sheet_answer("", [row])


def answer_sub_menu_number(user_id, question):
    q = str(question or "").strip()

    if not q.isdigit():
        return None

    state = get_user_state(user_id)

    if not state:
        return None

    sheet_name = state.get("sheet_name")

    if not sheet_name:
        return None

    rows = sheet_api.read_sheet(sheet_name)

    index = int(q) - 1

    if index < 0 or index >= len(rows):
        return (
            "Số thứ tự không hợp lệ. "
            "Quý công dân vui lòng chọn đúng số trong danh sách thủ tục."
        )

    selected_row = rows[index]

    set_user_state(user_id, {
        "level": "procedure_detail",
        "sheet_name": sheet_name,
        "procedure": selected_row
    })

    return build_procedure_detail(selected_row)

def answer_menu_number(user_id, question):
    q = str(question or "").strip()

    if not q.isdigit():
        return None

    sheet_name = sheet_api.get_sheet_by_menu_number(q)

    if not sheet_name:
        return None

    if sheet_name in ["THONGTIN", "TRA_CUU_LIEN_HE", "FAQ"]:
        rows = sheet_api.read_sheet(sheet_name)
        return build_sheet_answer(question, rows[:3])

    set_user_state(user_id, {
        "level": "procedure_list",
        "sheet_name": sheet_name
    })

    return build_procedure_list(sheet_name)

def get_menu_row_by_sheet(sheet_name):
    if not sheet_name:
        return None

    menu_rows = sheet_api.read_menu()

    for row in menu_rows:
        row_sheet = sheet_api.get_menu_sheet_name(row)

        if str(row_sheet).strip() == str(sheet_name).strip():
            return row

    return None

def answer_context_question(user_id, question):
    q = str(question or "").lower().strip()
    state = get_user_state(user_id)

    if not state:
        return None

    procedure = state.get("procedure")

    if not procedure:
        return None

    sheet_name = (
        state.get("sheet_name")
        or procedure.get("_SOURCE_SHEET", "")
    )

    menu_row = get_menu_row_by_sheet(sheet_name)

    # ===== VỊ TRÍ / GOOGLE MAP =====
    if any(k in q for k in [
        "vị trí",
        "vi tri",
        "bản đồ",
        "ban do",
        "google map",
        "map",
        "đường đi",
        "duong di"
    ]):
        google_map = ""

        if menu_row:
            google_map = (
                menu_row.get("GOOGLE_MAP")
                or menu_row.get("Google Map")
                or menu_row.get("MAP")
                or menu_row.get("LINK_MAP")
                or ""
            )

        if google_map:
            return f"🗺️ Vị trí trên Google Maps:\n{google_map}"

        return "Hiện hệ thống chưa cập nhật Google Maps cho nội dung này."

    # ===== CƠ QUAN THỰC HIỆN =====
    if any(k in q for k in [
        "ở đâu",
        "làm ở đâu",
        "thực hiện ở đâu",
        "thực hiện ở dâu",
        "địa điểm",
        "đến đâu làm",
        "cơ quan nào",
        "nơi thực hiện",
        "địa điểm thực hiện",
        "nộp ở đâu"
    ]):
        co_quan = procedure.get("CO_QUAN_THUC_HIEN") or ""

        if co_quan:
            return f"📍 Cơ quan thực hiện:\n{co_quan}"

        return "Hiện hệ thống chưa cập nhật thông tin cơ quan thực hiện của thủ tục này."

   # ===== HỒ SƠ / GIẤY TỜ =====
    if any(k in q for k in [
        "hồ sơ",
        "giấy tờ",
        "cần gì",
        "cần giấy",
        "có cần",
        "chuẩn bị gì",
        "mang gì",
        "giấy khai sinh"
    ]):
        ho_so = procedure.get("HO_SO") or ""

        if ho_so:
            return f"📄 Hồ sơ cần chuẩn bị:\n{ho_so}"

        return "Hiện hệ thống chưa cập nhật thông tin hồ sơ của thủ tục này."

    # ===== TRÌNH TỰ =====
    if any(k in q for k in [
        "trình tự",
        "các bước",
        "làm thế nào",
        "thực hiện thế nào",
        "quy trình"
    ]):
        trinh_tu = procedure.get("TRINH_TU") or ""

        if trinh_tu:
            return f"📝 Trình tự thực hiện:\n{trinh_tu}"

        return "Hiện hệ thống chưa cập nhật trình tự thực hiện của thủ tục này."

    # ===== THỜI HẠN =====
    if any(k in q for k in [
        "bao lâu",
        "thời hạn",
        "mấy ngày",
        "khi nào có",
        "bao nhiêu ngày"
    ]):
        thoi_han = procedure.get("THOI_HAN") or ""

        if thoi_han:
            return f"⏱ Thời hạn giải quyết:\n{thoi_han}"

        return "Hiện hệ thống chưa cập nhật thời hạn giải quyết của thủ tục này."

    # ===== LỆ PHÍ =====
    if any(k in q for k in [
        "lệ phí",
        "phí",
        "bao nhiêu tiền",
        "mất tiền không",
        "có mất phí không"
    ]):
        le_phi = procedure.get("LE_PHI") or ""

        if le_phi:
            return f"💰 Lệ phí:\n{le_phi}"

        return "Hiện hệ thống chưa cập nhật thông tin lệ phí của thủ tục này."

    # ===== DỊCH VỤ CÔNG / ONLINE =====
    if any(k in q for k in [
        "online",
        "trực tuyến",
        "làm online",
        "dịch vụ công",
        "link",
        "nộp online"
    ]):
        link = procedure.get("LINK_DVC") or ""

        if link:
            return f"🔗 Link dịch vụ công:\n{link}"

        return "Hiện hệ thống chưa cập nhật link dịch vụ công của thủ tục này."

    # ===== ĐIỀU KIỆN =====
    if any(k in q for k in [
        "điều kiện",
        "đủ điều kiện",
        "ai được làm",
        "đối tượng"
    ]):
        dieu_kien = procedure.get("DIEU_KIEN") or ""

        if dieu_kien:
            return f"✅ Điều kiện thực hiện:\n{dieu_kien}"

        return "Hiện hệ thống chưa cập nhật điều kiện thực hiện của thủ tục này."

    # ===== KẾT QUẢ =====
    if any(k in q for k in [
        "kết quả",
        "nhận gì",
        "được gì"
    ]):
        ket_qua = procedure.get("KET_QUA") or ""

        if ket_qua:
            return f"📌 Kết quả thực hiện:\n{ket_qua}"

        return "Hiện hệ thống chưa cập nhật kết quả thực hiện của thủ tục này."

    return None

#========== NHẬN DIỆN MENU ==========
def answer_menu_keyword(user_id, question):
    sheet_name = sheet_api.get_sheet_by_menu_keyword(question)

    if not sheet_name:
        return None

    if sheet_name in ["THONGTIN", "TRA_CUU_LIEN_HE", "FAQ"]:
        rows = sheet_api.read_sheet(sheet_name)
        return build_sheet_answer(question, rows[:3])

    set_user_state(user_id, {
        "level": "procedure_list",
        "sheet_name": sheet_name
    })

    return build_procedure_list(sheet_name)

def build_answer(user_id, question):
    answer = router_service.greeting_router(
        user_id,
        question,
        answer_greeting,
        clear_user_state
    )

    if not answer:
        answer = router_service.contact_router(
            user_id,
            question,
            sheet_api,
            user_states
        )

    if not answer:
        answer = router_service.procedure_router(
            user_id,
            question,
            answer_context_question,
            answer_sub_menu_number,
            answer_menu_number,
            answer_menu_keyword
        )

    if not answer:
        answer = router_service.search_router(
            user_id,
            question,
            sheet_api,
            build_sheet_answer,
            set_user_state,
            lambda question: False,
            build_search_options
        )

    if not answer:
        answer = (
            "Xin lỗi, hiện hệ thống chưa tìm thấy nội dung phù hợp. "
            "Quý công dân vui lòng nhập rõ hơn nội dung cần hỏi hoặc nhập 'menu' "
            "để quay lại danh mục hỗ trợ."
        )

    sheet_api.append_chat_history(
        user_id=user_id,
        user_message=question,
        bot_reply=answer
    )

    return answer
    
@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "bot": BOT_NAME,
        "message": "Bot đang hoạt động"
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })


@app.route("/test-sheet")
def test_sheet():
    try:
        menu = sheet_api.read_menu()

        return jsonify({
            "status": "ok",
            "menu_count": len(menu),
            "sample": menu[:3]
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/test-ai", methods=["POST", "GET"])
def test_ai():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        question = data.get("question", "")
    else:
        question = request.args.get(
            "q",
            "Xin chào"
        )

    answer = build_answer(
        user_id="test-web",
        question=question
    )

    return jsonify({
        "question": question,
        "answer": answer
    })


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({
            "status": "ok",
            "message": "Webhook OK"
        })

    data = request.get_json(silent=True) or {}

    try:
        event_name = data.get("event_name", "")

        if event_name != "user_send_text":
            return jsonify({
                "success": True,
                "message": "Ignored event"
            })

        message_id = (
            data.get("message", {}).get("msg_id")
            or data.get("message", {}).get("message_id")
            or ""
        )

        if message_id:
            if message_id in processed_messages:
                return jsonify({
                    "success": True,
                    "message": "Duplicate ignored"
                })

            processed_messages.add(message_id)

        user_id = (
            data.get("sender", {})
            .get("id", "")
        )

        message = (
            data.get("message", {})
            .get("text", "")
        )

        if not user_id or not message:
            return jsonify({
                "success": False,
                "message": "Missing user_id or message"
            }), 400

        remember(
            user_id=user_id,
            role="user",
            text=message
        )

        answer = build_answer(
            user_id=user_id,
            question=message
        )

        remember(
            user_id=user_id,
            role="assistant",
            text=answer
        )

        zalo_service.send_text(
            user_id=user_id,
            text=answer
        )

        return jsonify({
            "success": True
        })

    except Exception as e:
        print("WEBHOOK ERROR:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}

    user_id = data.get(
        "user_id",
        "web"
    )

    question = data.get(
        "question",
        ""
    )

    if not question:
        return jsonify({
            "success": False,
            "message": "Missing question"
        }), 400

    remember(
        user_id=user_id,
        role="user",
        text=question
    )

    answer = build_answer(
        user_id=user_id,
        question=question
    )

    remember(
        user_id=user_id,
        role="assistant",
        text=answer
    )

    return jsonify({
        "success": True,
        "answer": answer
    })


if __name__ == "__main__":
    app.run(
        host=HOST,
        port=PORT
    )
