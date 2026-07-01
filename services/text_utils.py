import re
import unicodedata


def normalize_text(text):
    if text is None:
        return ""
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9\s,./:;_\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_first(row, *keys, default=""):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def safe_int(value, default=999):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def split_keywords(value):
    text = normalize_text(value)
    return [x.strip() for x in re.split(r"[,;\n]+", text) if x.strip()]


def compact(value, limit=1500):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit - 20].rstrip() + "..."
