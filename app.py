
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
# LOAD KNOWLEDGE
# ==========================================
try:
    with open("knowledge.json", "r", encoding="utf-8") as f:
        DATA = json.load(f)
except:
    DATA = {}

KNOWLEDGE = DATA.get("knowledge", [])
PHONE = DATA.get("phone", "")
ADDRESS1 = DATA.get("address1", "")
ADDRESS2 = DATA.get("address2", "")
FANPAGE = DATA.get("fanpage", "")
OA_NAME = DATA.get("oa_name", "Công an phường Phù Liễn")

# ==========================================
# SEARCH KNOWLEDGE
# ==========================================
def search_knowledge(question):

    q = question.lower().strip()

    if "điện thoại" in q or "số điện thoại" in q:
        return f"Số điện thoại của {OA_NAME}: {PHONE}"

    if "địa chỉ" in q:
        return f"{ADDRESS1}\n{ADDRESS2}"

    if "fanpage" in q or "facebook" in q:
        return f"Fanpage:\n{FANPAGE}"

    for item in KNOWLEDGE:

        ask = item.get("question", "").lower().strip()

        if not ask:
            continue

        if ask in q or q in ask:
            return item.get("answer")

        words = ask.split()

        if any(word in q for word in words):
            return item.get("answer")

    return None


# ==========================================
# GEMINI
# ==========================================
def ask_gemini(question):

    q = question.lower().strip()

    if any(x in q for x in [
        "bạn làm được gì",
        "hỗ trợ gì",
        "cú pháp",
        "hướng dẫn",
        "sử dụng bot"
    ]):
        return f"""
Xin chào! Tôi là trợ lý ảo của {OA_NAME}.

Tôi có thể hỗ trợ:

• Số điện thoại, địa chỉ Công an phường.
• Hướng dẫn cấp căn cước.
• Hướng dẫn cư trú, tạm trú, thường trú.
• Giải đáp Đề án 06.
• Hướng dẫn định danh điện tử VNeID.
• Hướng dẫn dịch vụ công trực tuyến.
• Tuyên truyền pháp luật.
• Giải đáp các nội dung liên quan đến Công an phường.

Ví dụ:
- Số điện thoại Công an phường?
- Địa chỉ Công an phường?
- Làm căn cước cần gì?
- Đăng ký tạm trú như thế nào?
- Đề án 06 là gì?
"""

    local_data = search_knowledge(question)

    prompt = f"""
Bạn là trợ lý ảo của {OA_NAME}.

Thông tin nội bộ:
{local_data if local_data else "Không có dữ liệu nội bộ."}

Nhiệm vụ:
- Hỗ trợ người dân về thủ tục hành chính.
- Cư trú.
- Căn cước.
- Đề án 06.
- Định danh điện tử.
- Dịch vụ công.
- Thông tin của Công an phường.

Nếu có dữ liệu nội bộ thì ưu tiên sử dụng.

Nếu câu hỏi ngoài phạm vi trên thì trả lời:

"Tôi là trợ lý ảo của {OA_NAME}. Hiện tôi hỗ trợ các nội dung liên quan đến thủ tục hành chính, cư trú, căn cước, Đề án 06 và hoạt động của Công an phường."

Trả lời ngắn gọn, lịch sự, dễ hiểu.

Câu hỏi:
{question}
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        print("GEMINI ERROR:", e)

        if local_data:
            return local_data

        return (
            "Xin lỗi, hiện tôi chưa có thông tin về nội dung này. "
            f"Quý công dân vui lòng liên hệ {OA_NAME} để được hỗ trợ."
        )


# ==========================================
# HOME
# ==========================================
@app.route("/")
def home():
    return f"{OA_NAME} đang hoạt động!"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ==========================================
# MINI APP API
# ==========================================
@app.route("/api/chat", methods=["POST"])
def api_chat():

    data = request.get_json()

    question = data.get("question", "")

    answer = ask_gemini(question)

    return jsonify({
        "answer": answer
    })


# ==========================================
# SEND MESSAGE
# ==========================================
def send_message(user_id, message):

    url = "https://openapi.zalo.me/v2.0/oa/message"

    headers = {
        "access_token": ZALO_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "recipient": {
            "user_id": str(user_id)
        },
        "message": {
            "text": str(message)[:1900]
        }
    }

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
# PRIVACY
# ==========================================
@app.route("/privacy")
def privacy():
    return "Chính sách bảo mật của Công an phường Phù Liễn."


# ==========================================
# TERMS
# ==========================================
@app.route("/terms")
def terms():
    return "Điều khoản sử dụng của Công an phường Phù Liễn."


# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
