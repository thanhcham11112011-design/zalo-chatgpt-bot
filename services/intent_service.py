import re


def normalize_text(text):
    text = str(text or "").lower().strip()

    text = text.replace("đ", "d")

    text = re.sub(r"\s+", " ", text)

    return text


# ==========================================
# CẢM ƠN / KẾT THÚC HỘI THOẠI
# ==========================================
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
        "bye",
        "goodbye"
    ]

    return any(word in q for word in keywords)


# ==========================================
# LỜI CHÀO
# ==========================================
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


# ==========================================
# KHÔNG NHẬN DIỆN CÂU HỎI NGOÀI LUỒNG
# ==========================================
def is_general_question(question):
    return False


# ==========================================
# PHÂN LOẠI Ý ĐỊNH
# ==========================================
def detect_intent(question):

    if is_thanks(question):
        return "THANKS"

    if is_greeting(question):
        return "GREETING"

    return "ADMIN_PROCEDURE"
