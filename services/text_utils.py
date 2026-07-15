"""
text_utils.py - BOT CAP 3.1
Lớp tiện ích kỹ thuật: chuẩn hóa chuỗi, lấy dữ liệu an toàn, tách từ khóa và rút gọn văn bản.
Không chứa dữ liệu nghiệp vụ, không đọc knowledge.json, không truy cập Google Sheets.
"""

import re
import unicodedata
from typing import Any, Dict, Iterable


# Chức năng: Chuẩn hóa chuỗi tiếng Việt về dạng không dấu, chữ thường.
# Vai trò: Tạo đầu vào thống nhất cho tìm kiếm, định tuyến và so khớp dữ liệu.
def normalize_text(text: Any) -> str:
    if text is None:
        return ""

    value = str(text).strip().lower()
    if not value:
        return ""

    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d")
    value = re.sub(r"[,./:;]+", " ", value)
    value = re.sub(r"[^a-z0-9\s_\-#]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


# Chức năng: Chuẩn hóa tên khóa/cột dữ liệu.
# Vai trò: Giúp các module đọc dict ổn định khi tên cột có khoảng trắng hoặc khác kiểu chữ.
def normalize_key(key: Any) -> str:
    return str(key or "").strip().upper()


# Chức năng: Lấy giá trị đầu tiên có dữ liệu từ một dict theo danh sách khóa.
# Vai trò: Hỗ trợ tương thích nhiều biến thể tên cột trong Google Sheets.
def get_first(row: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    if not isinstance(row, dict):
        return default

    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value

        normalized = normalize_key(key)
        if normalized != key:
            value = row.get(normalized)
            if value not in (None, ""):
                return value

    return default


# Chức năng: Chuyển giá trị sang số nguyên an toàn.
# Vai trò: Tránh lỗi khi chấm điểm, sắp xếp ưu tiên hoặc xử lý phân trang.
def safe_int(value: Any, default: int = 999) -> int:
    try:
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


# Chức năng: Chia chuỗi thành danh sách phần tử theo nhiều dấu phân cách.
# Vai trò: Dùng chung cho các cột nhiều giá trị như từ khóa, địa bàn, gợi ý.
def split_list(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []

    parts = re.split(r"[,;\n|]+", text)
    return [item.strip() for item in parts if item and item.strip()]


# Chức năng: Tách chuỗi từ khóa thành danh sách từ khóa đã chuẩn hóa.
# Vai trò: Hỗ trợ các hàm chấm điểm tìm kiếm theo dữ liệu Google Sheets.
def split_keywords(value: Any) -> list[str]:
    return [normalize_text(item) for item in split_list(value) if normalize_text(item)]


# Chức năng: Rút gọn văn bản theo giới hạn ký tự.
# Vai trò: Bảo đảm nội dung trả lời phù hợp giới hạn tin nhắn và dễ đọc.
def compact(value: Any, limit: int = 1500) -> str:
    text = str(value or "").strip()
    limit = safe_int(limit, default=1500)

    if limit <= 0:
        return ""

    if len(text) <= limit:
        return text

    if limit <= 20:
        return text[:limit].rstrip()

    return text[: limit - 3].rstrip() + "..."


# Chức năng: Kiểm tra chuỗi có rỗng sau chuẩn hóa hay không.
# Vai trò: Giúp các module bỏ qua dữ liệu trống trước khi tìm kiếm hoặc định tuyến.
def is_blank(value: Any) -> bool:
    return normalize_text(value) == ""


# Chức năng: Loại bỏ phần tử trống trong danh sách chuỗi.
# Vai trò: Chuẩn hóa danh sách dữ liệu kỹ thuật trước khi ghép hoặc hiển thị.
def remove_blank(items: Iterable[Any]) -> list[str]:
    result = []
    for item in items or []:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result
