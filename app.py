# app.py

from flask import Flask, request, jsonify
from flask_cors import CORS

from config import PORT, BOT_NAME, DEFAULT_REPLY, check_config
from router import route_message_for_ai, get_welcome_message
from gemini_ai import ask_gemini
from zalo_service import send_zalo_text
from logger import write_log, log_error


app = Flask(__name__)
CORS(app)

processed_messages = set()


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "bot": BOT_NAME,
        "message": "Bot đang hoạt động"
    })


@app.route("/health", methods=["GET"])
def health():
    ok, missing = check_config()

    return jsonify({
        "status": "ok" if ok else "missing_config",
        "missing": missing
    })


@app.route("/test-ai", methods=["GET", "POST"])
def test_ai():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        question = data.get("question", "")
    else:
        question = request.args.get("q", "menu")

    result = build_answer(
        user_id="test-web",
        question=question
    )

    return jsonify({
        "success": True,
        "question": question,
        "answer": result["answer"],
        "source": result["source"]
    })


def build_answer(user_id, question):
    routed = route_message_for_ai(question)

    answer = routed.get("reply", DEFAULT_REPLY)
    source = routed.get("source", "DEFAULT")
    use_ai = routed.get("use_ai", False)

    if use_ai:
        answer = ask_gemini(question)
        source = "GEMINI_AI"

    write_log(
        user_id=user_id,
        user_message=question,
        bot_reply=answer,
        source=source
    )

    return {
        "answer": answer,
        "source": source
    }


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({
            "status": "ok",
            "message": "Webhook OK"
        }), 200

    data = request.get_json(silent=True) or {}

    try:
        print("WEBHOOK DATA:", data)

        event_name = data.get("event_name", "")
        user_id = data.get("sender", {}).get("id", "")
        message_data = data.get("message", {}) or {}

        if not user_id:
            return jsonify({
                "success": False,
                "message": "Missing user_id"
            }), 400

        if event_name != "user_send_text":
            send_zalo_text(
                user_id=user_id,
                message=get_welcome_message()
            )

            return jsonify({
                "success": True,
                "message": "Non-text event handled"
            }), 200

        message_id = (
            message_data.get("msg_id")
            or message_data.get("message_id")
            or ""
        )

        if message_id:
            if message_id in processed_messages:
                return jsonify({
                    "success": True,
                    "message": "Duplicate ignored"
                }), 200

            processed_messages.add(message_id)

        user_text = message_data.get("text", "")

        if not user_text:
            send_zalo_text(
                user_id=user_id,
                message=get_welcome_message()
            )

            return jsonify({
                "success": True,
                "message": "Empty text handled"
            }), 200

        result = build_answer(
            user_id=user_id,
            question=user_text
        )

        send_zalo_text(
            user_id=user_id,
            message=result["answer"]
        )

        return jsonify({
            "success": True,
            "source": result["source"]
        }), 200

    except Exception as e:
        error_message = f"Lỗi xử lý webhook: {e}"
        print("[WEBHOOK ERROR]", error_message)

        try:
            user_id = data.get("sender", {}).get("id", "")
            user_text = data.get("message", {}).get("text", "")

            if user_id:
                send_zalo_text(
                    user_id=user_id,
                    message=DEFAULT_REPLY
                )

            log_error(
                user_id=user_id,
                user_message=user_text,
                error_message=error_message
            )

        except Exception as log_e:
            print("[WEBHOOK LOG ERROR]", log_e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 200


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}

    user_id = data.get("user_id", "web")
    question = data.get("question", "")

    if not question:
        return jsonify({
            "success": False,
            "message": "Missing question"
        }), 400

    result = build_answer(
        user_id=user_id,
        question=question
    )

    return jsonify({
        "success": True,
        "answer": result["answer"],
        "source": result["source"]
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=PORT
    )
