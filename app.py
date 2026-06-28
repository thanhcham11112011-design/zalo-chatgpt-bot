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
            "8. Thông tin đơn vị\n"
            "9. Tra cứu liên hệ"
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

def answer_context_question(user_id, question):
    q = str(question or "").lower().strip()
    state = get_user_state(user_id)

    if not state:
        return None

    procedure = state.get("procedure")

    if not procedure:
        return None

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

    if any(k in q for k in [
        "hồ sơ",
        "giấy tờ",
        "cần gì",
        "chuẩn bị gì",
        "mang gì"
    ]):
        ho_so = procedure.get("HO_SO") or ""

        if ho_so:
            return f"📄 Hồ sơ cần chuẩn bị:\n{ho_so}"

        return "Hiện hệ thống chưa cập nhật thông tin hồ sơ của thủ tục này."

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

    return None

def build_answer(user_id, question):
    greeting_answer = answer_greeting(question)

    if greeting_answer:
        clear_user_state(user_id)
        answer = greeting_answer
    else:
        context_answer = answer_context_question(
            user_id,
            question
        )

        if context_answer:
            answer = context_answer
        else:
            sub_menu_answer = answer_sub_menu_number(
                user_id,
                question
            )

            if sub_menu_answer:
                answer = sub_menu_answer
            else:
                menu_number_answer = answer_menu_number(
                    user_id,
                    question
                )

                if menu_number_answer:
                    answer = menu_number_answer
                else:
                    context_items = sheet_api.search(
                        question,
                        limit=5
                    )

                    sheet_answer = build_sheet_answer(
                        question,
                        context_items
                    )

                    if sheet_answer:
                        if context_items:
                            set_user_state(user_id, {
                                "level": "procedure_detail",
                                "sheet_name": context_items[0].get("_SOURCE_SHEET", ""),
                                "procedure": context_items[0]
                            })

                        answer = sheet_answer
                    else:
                        try:
                            history_text = get_history_text(user_id)

                            answer = gemini_service.ask(
                                question=question,
                                context_items=context_items,
                                history_text=history_text
                            )

                        except Exception as e:
                            print("GEMINI FALLBACK ERROR:", e)

                            answer = (
                                "Xin lỗi, hiện hệ thống chưa tìm thấy nội dung phù hợp trong dữ liệu. "
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
