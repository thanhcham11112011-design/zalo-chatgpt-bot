from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import google.generativeai as genai
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ==========================
# CONFIG
# ==========================
ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================
# LOAD DATA
# ==========================
with open("knowledge.json", "r", encoding="utf-8") as f:
    DATA = json.load(f)

SERVICES = DATA.get("services", {})
OA_NAME = DATA.get("oa_name", "Công an phường Phù Liễn")
ADDRESS1 = DATA.get("address1", "")
ADDRESS2 = DATA.get("address2", "")
PHONE = DATA.get("phone", "")

# ==========================
# MEMORY
# ==========================
conversation_memory = {}

def remember(user_id, role, text):
    history = conversation_memory.get(user_id, [])
    history.append({
        "role": role,
        "text": text
    })

    if len(history) > 10:
        history = history[-10:]

    conversation_memory[user_id] = history


def get_history(user_id):
    history = conversation_memory.get(user_id, [])
    text = ""

    for item in history:
        text += f"{item['role']}: {item['text']}\n"

    return text


# ==========================
# LOG
# ==========================
def write_log(user_id, question, answer):
    try:
        with open(
            "chat.log",
            "a",
            encoding="utf-8"
        ) as f:
            f.write(
                f"{datetime.now()} | "
                f"{user_id} | "
                f"{question} | "
                f"{answer}\n"
            )
    except:
        pass


# ==========================
# DETECT SERVICE
# ==========================
def detect_service(question):

    q = question.lower()

    for key, service in SERVICES.items():

        for keyword in service.get(
            "keywords",
            []
        ):

            if keyword.lower() in q:
                return key

    return None


# ==========================
# DETECT FIELD
# ==========================
def detect_field(question):

    q = question.lower()

    if any(x in q for x in [
        "ở đâu",
        "địa chỉ",
        "nơi làm",
        "làm ở đâu"
    ]):
        return "dia_diem"

    if any(x in q for x in [
        "giấy tờ",
        "hồ sơ",
        "cần gì",
        "mang gì"
    ]):
        return "ho_so"

    if any(x in q for x in [
        "bao lâu",
        "mấy ngày",
        "thời gian"
    ]):
        return "thoi_han"

    if any(x in q for x in [
        "bao nhiêu tiền",
        "lệ phí",
        "mất phí",
        "phí"
    ]):
        return "le_phi"

    if any(x in q for x in [
        "thủ tục",
        "trình tự",
        "các bước"
    ]):
        return "trinh_tu"

    return None


# ==========================
# LOCAL ANSWER
# ==========================
def answer_service(question):

    service = detect_service(question)

    if not service:
        return None

    data = SERVICES.get(service)

    field = detect_field(question)

    if not field:

        return (
            f"Quý công dân đang hỏi về:\n"
            f"{data['name']}\n\n"
            "Xin vui lòng cho biết:\n"
            "• Địa điểm thực hiện\n"
            "• Hồ sơ cần chuẩn bị\n"
            "• Thời hạn giải quyết\n"
            "• Lệ phí\n"
            "• Trình tự thực hiện"
        )

    value = data.get(field)

    if not value:
        return None

    if isinstance(value, list):

        text = ""

        for i, item in enumerate(
            value,
            start=1
        ):
            text += f"{i}. {item}\n"

        return text

    return value


# ==========================
# GEMINI
# ==========================
def ask_gemini(user_id, question):

    local = answer_service(question)

    if local:
        return local

    history = get_history(user_id)

    prompt = f"""
Bạn là trợ lý ảo của Công an phường Phù Liễn.

Thông tin:
- Địa chỉ 1:
{ADDRESS1}

- Địa chỉ 2:
{ADDRESS2}

Nếu câu hỏi không có trong dữ liệu,
hãy trả lời mang tính tham khảo
và hướng dẫn người dân liên hệ
Công an phường hoặc tra cứu
Cổng Dịch vụ công Bộ Công an.

Lịch sử:
{history}

Câu hỏi:
{question}
"""

    try:
        response = model.generate_content(
            prompt
        )

        return response.text

    except Exception as e:

        print("GEMINI ERROR:", e)

        return (
            "Xin lỗi, hiện hệ thống đang bận. "
            "Quý công dân vui lòng thử lại sau."
        )


# ==========================
# SEND MESSAGE
# ==========================
def send_message(
    user_id,
    message
):

    url = (
        "https://openapi.zalo.me"
        "/v2.0/oa/message"
    )

    headers = {
        "access_token":
            ZALO_ACCESS_TOKEN,
        "Content-Type":
            "application/json"
    }

    payload = {
        "recipient": {
            "user_id":
                str(user_id)
        },
        "message": {
            "text":
                message[:1900]
        }
    }

    requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )


# ==========================
# HOME
# ==========================
@app.route("/")
def home():
    return (
        "Trợ lý ảo Công an "
        "phường Phù Liễn "
        "đang hoạt động."
    )


# ==========================
# WEBHOOK
# ==========================
@app.route(
    "/webhook",
    methods=["POST", "GET"]
)
def webhook():

    if request.method == "GET":
        return "Webhook OK"

    data = request.json

    try:

        if (
            data
            and data.get(
                "event_name"
            ) == "user_send_text"
        ):

            user_id = data["sender"]["id"]
            text = data["message"]["text"]

            remember(
                user_id,
                "user",
                text
            )

            answer = ask_gemini(
                user_id,
                text
            )

            remember(
                user_id,
                "assistant",
                answer
            )

            write_log(
                user_id,
                text,
                answer
            )

            send_message(
                user_id,
                answer
            )

    except Exception as e:
        print(e)

    return jsonify({
        "success": True
    })


# ==========================
# API MINI APP
# ==========================
@app.route(
    "/api/chat",
    methods=["POST"]
)
def api_chat():

    data = request.get_json()

    user_id = data.get(
        "user_id",
        "web"
    )

    question = data.get(
        "question",
        ""
    )

    answer = ask_gemini(
        user_id,
        question
    )

    return jsonify({
        "answer":
            answer
    })


# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000
            )
        )
    )
