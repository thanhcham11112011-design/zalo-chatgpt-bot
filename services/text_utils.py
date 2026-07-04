import re
import unicodedata


# Chức năng: Chuẩn hóa văn bản tiếng Việt để phục vụ tìm kiếm.
# Vai trò: Đưa toàn bộ dữ liệu về cùng một chuẩn trước khi chấm điểm.
def normalize_text(text):
    if text is None:
        return ""

    text = str(text).strip().lower()

    text = unicodedata.normalize("NFD", text)
    text = "".join(
        ch for ch in text
        if unicodedata.category(ch) != "Mn"
    )

    text = text.replace("đ", "d")

    text = re.sub(r"[^a-z0-9\s,./:;_\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# Chức năng: Lấy giá trị đầu tiên khác rỗng theo danh sách cột.
# Vai trò: Hỗ trợ BOT đọc dữ liệu linh hoạt giữa các Sheet.
def get_first(row, *keys, default=""):
    if not isinstance(row, dict):
        return default

    for key in keys:
        value = row.get(key)

        if value not in (None, ""):
            return value

    return default


# Chức năng: Chuyển giá trị sang số nguyên an toàn.
# Vai trò: Đọc MUC_UU_TIEN, PAGE, SCORE... mà không gây lỗi.
def safe_int(value, default=999):
    try:
        return int(str(value).strip())
    except Exception:
        return default


# Chức năng: Tách chuỗi từ khóa trong Google Sheets thành danh sách.
# Vai trò: Phục vụ tìm kiếm MENU, FAQ, THỦ TỤC và TRA_CUU_LIEN_HE.
def split_keywords(value):
    text = normalize_text(value)

    if not text:
        return []

    return [
        item.strip()
        for item in re.split(r"[,;\n|]+", text)
        if item.strip()
    ]


# Chức năng: Rút gọn văn bản theo số ký tự tối đa.
# Vai trò: Đảm bảo nội dung trả lời không vượt giới hạn của Zalo OA.
def compact(value, limit=1500):
    text = str(value or "").strip()

    if len(text) <= limit:
        return text

    return text[: limit - 3].rstrip() + "..."


# Chức năng: Kiểm tra chuỗi có phải số nguyên hay không.
# Vai trò: Hỗ trợ nhận diện lựa chọn menu và số thứ tự thủ tục.
def is_number(value):
    return str(value or "").strip().isdigit()


# Chức năng: Chuẩn hóa khoảng trắng trong chuỗi.
# Vai trò: Loại bỏ khoảng trắng thừa trước khi so khớp dữ liệu.
def normalize_space(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


# Chức năng: So khớp hai chuỗi sau khi chuẩn hóa.
# Vai trò: Tăng độ ổn định khi tìm kiếm tên thủ tục, cơ quan và cán bộ.
def text_equals(a, b):
    return normalize_text(a) == normalize_text(b)


# Chức năng: Kiểm tra chuỗi A có chứa chuỗi B sau khi chuẩn hóa.
# Vai trò: Hỗ trợ tìm kiếm gần đúng trong BOT CAP.
def text_contains(text, keyword):
    t = normalize_text(text)
    k = normalize_text(keyword)

    return bool(k and k in t)
