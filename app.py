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


def build_answer(user_id, question):
    context_items = sheet_api.search(
        question,
        limit=5
    )

    history_text = get_history_text(user_id)

    answer = gemini_service.ask(
        question=question,
        context_items=context_items,
        history_text=history_text
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
    question = ""

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        question = data.get("question", "")

    if request.method == "GET":
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
