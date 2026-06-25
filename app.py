from flask import Flask, request, jsonify
import requests
import os
import json
import google.generativeai as genai

app = Flask(__name__)

# ==========================================
# API KEY VÀ TOKEN
# ==========================================
# Khai báo trên Render -> Environment Variables
ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ==========================================
# KHỞI TẠO GEMINI
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================================
# ĐỌC DỮ LIỆU NGHIỆP VỤ
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
# TÌM KIẾM DỮ LIỆU
# ==========================================
def search_knowledge(question):
    question = question.lower()

    if "điện thoại" in question or "số điện thoại" in question:
        return f"Số điện thoại của {OA_NAME}: {PHONE}"

    if "địa chỉ" in question:
        return f"{ADDRESS1}\n{ADDRESS2}"

    if "fanpage" in question or "facebook" in question:
        return f"Fanpage của {OA_NAME}:\n{FANPAGE}"

    for item in KNOWLEDGE:
        q = item.get("question", "").lower()

        if q and q in question:
            return item.get("answer")

    return None


# ==========================================
# GỌI GEMINI
# ==========================================
def ask_gemini(user_question):
    data = search_knowledge(user_question)

    if data is None:
        return (
            "Xin lỗi, tôi chỉ hỗ trợ giải đáp các thủ tục hành chính, "
            "Đề án 06, cư trú, căn cước, định danh điện tử và các nội dung "
            "tuyên truyền của Công an phường Phù Liễn."
        )

    prompt = f"""
Bạn là trợ lý ảo của Công an phường Phù Liễn, TP Hải Phòng.

Chỉ được trả lời dựa trên thông tin sau:

{data}

Hãy trả lời ngắn gọn, lịch sự và chính xác.

Câu hỏi:
{user_question}
"""

    response = model.generate_content(prompt)
    return response.text


# ==========================================
# GỬI TIN NHẮN VỀ ZALO OA
# ==========================================
def send_message(user_id, message):

    url = "https://openapi.zalo.me/v3.0/oa/message/cs"

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

    r = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )

    print("ZALO RESPONSE:")
    print(r.text)


# ==========================================
# TRANG CHỦ
# ==========================================
@app.route("/")
def home():
    return "Bot Công an phường Phù Liễn đang hoạt động!"


# ==========================================
# KIỂM TRA TRẠNG THÁI
# ==========================================
@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })


# ==========================================
# XÁC THỰC DOMAIN ZALO
# ==========================================
@app.route("/zalo_verifierOSUoEQBmFXWfpPuEziTELNNX_6oPboOoDJWu.html")
def zalo_verify():
    return """
<!DOCTYPE html>
<html>
<head>
<meta property="zalo-platform-site-verification"
content="OSUoEQBmFXWfpPuEziTELNNX_6oPboOoDJWu" />
</head>
<body>
There Is No Limit To What You Can Accomplish Using Zalo!
</body>
</html>
"""


# ==========================================
# WEBHOOK NHẬN TIN NHẮN TỪ ZALO
# ==========================================
@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    if request.method == "GET":
        return "Webhook OK", 200

    data = request.json

    print("===== ZALO EVENT =====")
    print(data)

    try:
        if data and data.get("event_name") == "user_send_text":

            user_id = data["sender"]["id"]
            text = data["message"]["text"]

            print("USER:", text)

            answer = ask_gemini(text)

            send_message(
                user_id,
                answer
            )

    except Exception as e:
        print("ERROR:", str(e))

    return jsonify({
        "success": True
    })


# ==========================================
# CHẠY FLASK
# ==========================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
