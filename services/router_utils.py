from services.text_utils import normalize_text, get_first


# Chức năng: Tách danh sách từ khóa từ một ô dữ liệu Google Sheets.
# Vai trò: Dùng thống nhất dữ liệu TU_KHOA trong các bộ định tuyến.
def _split_keywords(value):
    raw = str(value or "").replace(";", ",").replace("|", ",")
    return [
        item.strip()
        for item in raw.split(",")
        if item and item.strip()
    ]


# Chức năng: Kiểm tra một dòng dữ liệu có trạng thái hoạt động hay không.
# Vai trò: Bảo đảm hệ thống chỉ xử lý các dòng đang bật trong Google Sheets.
def _is_on(row):
    status = normalize_text(
        get_first(
            row,
            "TRANG_THAI",
            "STATUS",
            default="ACTIVE",
        )
    )
    return status not in [
        "off",
        "inactive",
        "false",
        "0",
        "no",
        "khong",
        "ngung",
        "dung",
    ]


# Chức năng: Lấy mã thủ tục chuẩn từ một dòng thủ tục.
# Vai trò: Dùng thống nhất mã thủ tục theo cấu trúc Google Sheets hiện hành.
def _procedure_id(row):
    return get_first(
        row,
        "MA_THU_TUC",
        "MÃ_THỦ_TỤC",
        "ID",
        "MA",
        "MÃ",
    )


# Chức năng: Tính độ dài chuỗi từ liên tiếp giống nhau giữa hai danh sách token.
# Vai trò: Hỗ trợ chấm điểm tên thủ tục và từ khóa mà không hardcode nghiệp vụ.
def _longest_contiguous_token_match(text_tokens, candidate_tokens):
    if not text_tokens or not candidate_tokens:
        return 0

    longest = 0
    previous = [0] * (len(candidate_tokens) + 1)

    for text_token in text_tokens:
        current = [0]

        for index, candidate_token in enumerate(
            candidate_tokens,
            start=1,
        ):
            if text_token == candidate_token:
                matched = previous[index - 1] + 1
                current.append(matched)
                longest = max(longest, matched)
            else:
                current.append(0)

        previous = current

    return longest


# Chức năng: Lấy giá trị THONGTIN theo tên khóa không phân biệt kiểu chữ.
# Vai trò: Hỗ trợ đọc dữ liệu đơn vị thống nhất từ Google Sheets.
def _thongtin_value(data, key):
    if not data or not key:
        return ""

    if key in data and data.get(key):
        return str(data.get(key)).strip()

    key_norm = normalize_text(key)

    for item_key, value in data.items():
        if normalize_text(item_key) == key_norm and value:
            return str(value).strip()

    return ""
