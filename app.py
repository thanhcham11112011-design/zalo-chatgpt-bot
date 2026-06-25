```python
from flask import Flask, request, jsonify
import requests
import os
import json
import google.generativeai as genai

app = Flask(__name__)

# =========================
# Biến môi trường trên Render
# =========================
ZALO_ACCESS_TOKEN = os.getenv("Z7cqH2g13z0WUQ140f4Rz1XPi4mMiNRa7KH8DTub_YmzNBs5TbGZLM6aYIX24LDz8P3XAEwDF-dbyEb0AaNBL2duhHG-yRlHAL2aRG-Tcb3q02NaqyMRyN28MKY_CGkLz0HXuUgT8o1CUEonmhLEw95LyKt2x4FOMQ7LQ7wWBqLrw94WdXNxw9bm77sAKKvCsQmqQGzbpenOuGHbrsYwt4pfvE6pZ4Bu_FMasOkuNkJOIIojM_3MQBXbGDrxP9CO1O0rESfjM_mz-Vt9jcnND6L5pNrwH2-mTMLv2IkiFyqm4UsaDx5F2251XLdQFBCvqPLH7FTmIoa9cMMuLiXE3QMXlCXofFvH6J7418OaqhMTGG1HZeXAGD7ju54gV5e0pPqyaPAuNcJ8SQtDnuIIM9WOD1YNwS9niI6AB7zmneLp-3W")
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6LzJLVxj7cXzg9zdiLHbfqq2437NaXPnUyEd-TtMBlkbQ")

# =========================
# Khởi tạo Gemini
# =========================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# =========================
# Đọc dữ liệu nghiệp vụ
# =========================
with open("knowledge.json", "r", encoding="utf-8") as f:
    DATA = json.load(f)

KNOWLEDGE = DATA.get("knowledge", [])
PHONE = DATA.get("phone", "")
ADDRESS1 = DATA.get("address1", "")
ADDRESS2 = DATA.get("address2", "")
FANPAGE = DATA.get("fanpage", "")
OA_NAME = DATA.get("oa_name", "Công an phường Phù Liễn")


# =========================
# Tìm thông tin trong kho dữ liệu
# =========================
def search_knowledge(question):
    question = question.lower()

    # Thông tin liên hệ
    if "điện thoại" in question or "số điện thoại" in question:
        return f"Số điện thoại của {OA_NAME}: {PHONE}"

    if "địa chỉ" in question:
        return f"{ADDRESS1}\n{ADDRESS2}"

    if "fanpage" in question or "facebook" in question:
        return f"Fanpage của {OA_NAME}:\n{FANPAGE}"

    # Tìm trong dữ liệu tập huấn
    for item in KNOWLEDGE:
        q = item.get("question", "").lower()

        if q and q in question:
            return item.get("answer")

    return None


# =========================
# Gọi Gemini
# =========================
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

Chỉ được phép trả lời dựa trên nội dung sau:

{data}

Hãy trả lời ngắn gọn, chính xác, lịch sự.

Câu hỏi của người dân:
{user_question}
"""

    response = model.generate_content(prompt)
    return response.text


# =========================
# Gửi tin nhắn về Zalo OA
# =========================
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

    print(r.text)


# =========================
# Trang chủ
# =========================
@app.route("/")
def home():
    return "Bot Công an phường Phù Liễn đang hoạt động!"


# =========================
# Kiểm tra trạng thái
# =========================
@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })


# =========================
# Webhook nhận tin nhắn Zalo
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    print("===== ZALO EVENT =====")
    print(data)

    try:
        if (
            data.get("event_name")
            == "user_send_text"
        ):
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


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
```
