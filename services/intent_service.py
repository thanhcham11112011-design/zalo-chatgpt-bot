import re


def normalize_text(text):
    text = str(text or "").lower().strip()
    text = text.replace("đ", "d")
    text = re.sub(r"\s+", " ", text)
    return text


def is_thanks(question):
    q = normalize_text(question)

    keywords = [
        "cam on",
        "cam on ban",
        "xin cam on",
        "thank",
        "thanks",
        "ok cam on",
        "duoc roi",
        "tam biet",
        "bye"
    ]

    return any(k in q for k in keywords)


def is_greeting(question):
    q = normalize_text(question)

    greetings = [
        "xin chao",
        "chao",
        "hello",
        "hi",
        "alo",
        "menu"
    ]

    return q in greetings


def is_general_question(question):
    q = normalize_text(question)

    general_keywords = [
        "tinh yeu",
        "tinh yeu la gi",
        "tình yêu",
        "tình yêu là gì",
        "thoi tiet",
        "thời tiết",
        "bong da",
        "bóng đá",
        "world cup",
        "ke chuyen",
        "kể chuyện",
        "ban la ai",
        "bạn là ai",
        "viet nam co bao nhieu",
        "việt nam có bao nhiêu",
        "hom nay la ngay nao",
        "hôm nay là ngày nào"
    ]

    return any(k in q for k in general_keywords)

def detect_intent(question):
    if is_thanks(question):
        return "THANKS"

    if is_greeting(question):
        return "GREETING"

    if is_general_question(question):
        return "GENERAL_AI"

    return "ADMIN_PROCEDURE"
