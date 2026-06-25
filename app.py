from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import json
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# ==========================================
# API KEY
# ==========================================
ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("TOKEN:", "OK" if ZALO_ACCESS_TOKEN else "MISSING")
print("GEMINI:", "OK" if GEMINI_API_KEY else "MISSING")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================================
# ĐỌC DỮ LIỆU
# ==========================================
with open("knowledge.json", "r", encoding="utf-8") as f:
    DATA = json.load(f)

KNOWLEDGE = DATA.get("knowledge", [])
PHONE = DATA.get("phone", "")
ADDRESS1 = DATA.get("address1", "")
ADDRESS2 = DATA.get("address2", "")
FANPAGE = DATA.get("fanpage", "")
OA_NAME = DATA.get("oa_name", "Công an phường Phù Liễn")

# ==========================================
# TÌM KIẾM TRI THỨC
# ==========================================
def search_knowledge(question):
    question = question.lower()

    if "điện thoại" in question:
        return f"Số điện thoại của {OA_NAME}: {PHONE}"

    if "địa chỉ" in question:
        return f"{ADDRESS1}\n{ADDRESS2}"

    if "fanpage" in question or "facebook" in question:
        return f"Fanpage:\n{FANPAGE}"

    for item in KNOWLEDGE:
        q = item.get("question", "").lower()

        if q and q in question:
            return item.get("answer")

    return None


# ==========================================
# GEMINI
# ==========================================
def ask_gemini(question):

    data = search_knowledge(question)

    if data is None:
        return (
            "Xin lỗi, tôi hiện chỉ hỗ trợ giải đáp thủ tục hành chính, "
            "Đề án 06, cư trú, căn cước, định danh điện tử và các nội dung "
            "tuyên truyền của Công an phường Phù Liễn."
        )

    prompt = f"""
Bạn là trợ lý ảo của Công an phường Phù Liễn.

Thông tin:

{data}

Hãy trả lời ngắn gọn, lịch sự.

Câu hỏi:
{question}
"""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print("GEMINI ERROR:", e)
        return data


# ==========================================
# TRANG CHỦ
# ==========================================
@app.route("/")
def home():
    return "Bot Công an phường Phù Liễn đang hoạt động!"


# ==========================================
# HEALTH
# ==========================================
@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })


# ==========================================
# API CHAT MINI APP
# ==========================================
@app.route("/api/chat", methods=["POST"])
def api_chat():

    data = request.get_json()

    question = data.get("question", "")

    print("MINI APP:", question)

    answer = ask_gemini(question)

    return jsonify({
        "answer": answer
    })


# ==========================================
# GỬI TIN NHẮN OA
# ==========================================
def send_message(user_id, message):

    url = "https://openapi.zalo.me/v3.0/oa/message"

    headers = {
        "access_token": ZALO_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "recipient": {
            "user_id": user_id
        },
        "message": {
            "text": message
        }
    }

    print("SEND TO:", user_id)
    print("MESSAGE:", message)

    try:
        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        print("STATUS:", r.status_code)
        print("RESPONSE:", r.text)

    except Exception as e:
        print("SEND ERROR:", e)


# ==========================================
# WEBHOOK
# ==========================================
@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    if request.method == "GET":
        return "Webhook OK"

    data = request.json

    print("===== ZALO EVENT =====")
    print(json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    ))

    try:
        if data and data.get("event_name") == "user_send_text":

            user_id = data["sender"]["id"]
            text = data["message"]["text"]

            print("USER:", user_id)
            print("TEXT:", text)

            answer = ask_gemini(text)

            print("ANSWER:", answer)

            send_message(
                user_id,
                answer
            )

    except Exception as e:
        print("WEBHOOK ERROR:", e)

    return jsonify({
        "success": True
    })


# ==========================================
# CHÍNH SÁCH BẢO MẬT
# ==========================================
@app.route("/privacy")
def privacy():
    return """
<html>
<head>
<meta charset="utf-8">
<title>Chính sách bảo mật</title>
</head>
<body style="font-family:Arial;padding:30px">
<h2>CHÍNH SÁCH BẢO MẬT</h2>

<p>
Cổng dịch vụ điện tử Công an phường Phù Liễn cam kết bảo vệ
thông tin cá nhân của người sử dụng.
</p>

<p>Thông tin được sử dụng nhằm:</p>

<ul>
<li>Giải quyết thủ tục hành chính.</li>
<li>Tư vấn, giải đáp cho người dân.</li>
<li>Tiếp nhận phản ánh, kiến nghị.</li>
<li>Đặt lịch làm việc.</li>
</ul>

<p>
Chúng tôi không chia sẻ thông tin cá nhân cho bên thứ ba,
trừ trường hợp theo quy định của pháp luật.
</p>
</body>
</html>
"""


# ==========================================
# ĐIỀU KHOẢN SỬ DỤNG
# ==========================================
@app.route("/terms")
def terms():
    return """
<html>
<head>
<meta charset="utf-8">
<title>Điều khoản sử dụng</title>
</head>
<body style="font-family:Arial;padding:30px">
<h2>ĐIỀU KHOẢN SỬ DỤNG</h2>

<p>
Mini App Công dịch vụ điện tử Công an phường Phù Liễn
được xây dựng nhằm hỗ trợ người dân tiếp cận thông tin
và thực hiện các dịch vụ công.
</p>

<p>Người sử dụng cam kết:</p>

<ul>
<li>Cung cấp thông tin trung thực.</li>
<li>Không sử dụng Mini App vào mục đích vi phạm pháp luật.</li>
<li>Không phát tán thông tin sai sự thật.</li>
</ul>

<p>
Công an phường Phù Liễn có quyền cập nhật nội dung
khi cần thiết.
</p>
</body>
</html>
"""


# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
