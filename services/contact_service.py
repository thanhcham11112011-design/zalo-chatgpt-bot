import re


CONTACT_SHEET = "TRA_CUU_LIEN_HE"


def normalize_text(text):
    text = str(text or "").lower().strip()
    text = text.replace("đ", "d")
    text = re.sub(r"\s+", " ", text)
    return text


CONTACT_MENU = [
    {
        "key": "CHI_HUY",
        "name": "Liên hệ chỉ huy Công an phường",
        "keywords": ["chỉ huy", "chi huy", "lãnh đạo", "lanh dao"]
    },
    {
        "key": "CSKV",
        "name": "Liên hệ bộ phận CSKV",
        "keywords": ["cskv", "cảnh sát khu vực", "canh sat khu vuc", "khu vực"]
    },
    {
        "key": "PCTP",
        "name": "Liên hệ bộ phận PCTP",
        "keywords": ["pctp", "phòng chống tội phạm", "phong chong toi pham"]
    },
    {
        "key": "AN",
        "name": "Liên hệ bộ phận An ninh",
        "keywords": ["an ninh", "an"]
    },
    {
        "key": "CNTT",
        "name": "Liên hệ tổ CNTT",
        "keywords": ["cntt", "công nghệ thông tin", "cong nghe thong tin"]
    },
    {
        "key": "DOAN_THANH_NIEN",
        "name": "Liên hệ đồng chí Bí thư ĐTNCS",
        "keywords": ["đoàn", "doan", "bí thư", "bi thu", "thanh niên", "thanh nien"]
    },
]


def build_contact_menu():
    lines = ["☎️ TRA CỨU THÔNG TIN LIÊN HỆ\n"]

    for index, item in enumerate(CONTACT_MENU, start=1):
        lines.append(f"{index}. {item['name']}")

    lines.append(
        "\nQuý công dân vui lòng nhập số thứ tự hoặc tên bộ phận cần liên hệ."
    )

    return "\n".join(lines)


def get_contact_key_from_question(question):
    q = normalize_text(question)

    if q.isdigit():
        index = int(q) - 1
        if 0 <= index < len(CONTACT_MENU):
            return CONTACT_MENU[index]["key"]

    for item in CONTACT_MENU:
        for kw in item["keywords"]:
            if normalize_text(kw) in q:
                return item["key"]

    return None


def get_value(row, columns):
    for col in columns:
        value = row.get(col)
        if value:
            return str(value).strip()
    return ""


def format_contact_row(row):
    ho_ten = get_value(row, ["HO_TEN", "HỌ_TÊN", "Ho ten", "Tên", "TEN"])
    chuc_vu = get_value(row, ["CHUC_VU", "CHỨC_VỤ", "Chức vụ"])
    dien_thoai = get_value(row, ["DIEN_THOAI", "ĐIỆN_THOẠI", "SDT", "SĐT", "So dien thoai"])
    bo_phan = get_value(row, ["BO_PHAN", "BỘ_PHẬN", "Bo phan"])
    tdp = get_value(row, ["TDP", "TO_DAN_PHO", "TỔ_DÂN_PHỐ", "To dan pho"])
    ghi_chu = get_value(row, ["GHI_CHU", "GHI_CHÚ", "Ghi chú"])

    lines = []

    if ho_ten:
        lines.append(f"👤 Họ tên: {ho_ten}")
    if chuc_vu:
        lines.append(f"💼 Chức vụ/Bộ phận: {chuc_vu}")
    elif bo_phan:
        lines.append(f"💼 Bộ phận: {bo_phan}")
    if tdp:
        lines.append(f"🏘️ Phụ trách: {tdp}")
    if dien_thoai:
        lines.append(f"☎️ Số điện thoại: {dien_thoai}")
    if ghi_chu:
        lines.append(f"📝 Ghi chú: {ghi_chu}")

    return "\n".join(lines)


def row_match_department(row, department_key):
    bo_phan = normalize_text(
        get_value(row, ["BO_PHAN", "BỘ_PHẬN", "Bo phan", "NHOM", "NHÓM"])
    )

    key = normalize_text(department_key)

    if key == "DOAN_THANH_NIEN":
        return (
            "doan" in bo_phan
            or "thanh nien" in bo_phan
            or "dtncs" in bo_phan
        )

    return key.lower() in bo_phan


def find_department_contacts(sheet_api, department_key):
    rows = sheet_api.read_sheet(CONTACT_SHEET)
    results = []

    for row in rows:
        if row_match_department(row, department_key):
            results.append(row)

    return results


def build_department_answer(sheet_api, department_key):
    rows = find_department_contacts(sheet_api, department_key)

    if not rows:
        return (
            "Xin lỗi, hiện hệ thống chưa tìm thấy nội dung phù hợp. "
            "Quý công dân vui lòng nhập rõ hơn nội dung cần hỏi hoặc nhập 'menu' "
            "để quay lại danh mục hỗ trợ."
        )

    lines = ["☎️ THÔNG TIN LIÊN HỆ\n"]

    for index, row in enumerate(rows, start=1):
        text = format_contact_row(row)
        if text:
            lines.append(f"{index}. {text}\n")

    return "\n".join(lines).strip()


def build_cskv_prompt():
    return (
        "Để tra cứu đúng đồng chí Cảnh sát khu vực phụ trách, "
        "Quý công dân vui lòng nhập tên hoặc số Tổ dân phố nơi cư trú/cần liên hệ.\n\n"
        "Ví dụ:\n"
        "- TDP số 1\n"
        "- Tổ dân phố số 5\n"
        "- Tôi ở TDP 7"
    )


def extract_tdp(question):
    q = normalize_text(question)

    match = re.search(r"(tdp|to dan pho|tổ dân phố|to)\s*(so|số)?\s*(\d+)", q)
    if match:
        return match.group(3)

    match = re.search(r"\b(\d+)\b", q)
    if match:
        return match.group(1)

    return ""


def find_cskv_by_tdp(sheet_api, question):
    tdp_number = extract_tdp(question)

    if not tdp_number:
        return None

    rows = find_department_contacts(sheet_api, "CSKV")
    results = []

    for row in rows:
        tdp = normalize_text(
            get_value(row, ["TDP", "TO_DAN_PHO", "TỔ_DÂN_PHỐ", "To dan pho"])
        )

        if tdp_number and tdp_number in tdp:
            results.append(row)

    if not results:
        return None

    lines = [f"👮 CẢNH SÁT KHU VỰC PHỤ TRÁCH TDP {tdp_number}\n"]

    for row in results:
        text = format_contact_row(row)
        if text:
            lines.append(text)

    return "\n\n".join(lines)


def start_contact_flow(user_id, user_states):
    user_states[user_id] = {
        "level": "contact_menu"
    }

    return build_contact_menu()


def handle_contact_flow(user_id, question, sheet_api, user_states):
    state = user_states.get(user_id)

    if not state:
        return None

    level = state.get("level")

    if level == "contact_menu":
        department_key = get_contact_key_from_question(question)

        if not department_key:
            return (
                "Nội dung nhập chưa phù hợp với danh sách tra cứu liên hệ. "
                "Quý công dân vui lòng nhập số thứ tự hoặc tên bộ phận cần liên hệ."
            )

        if department_key == "CSKV":
            user_states[user_id] = {
                "level": "contact_cskv",
                "department": "CSKV"
            }
            return build_cskv_prompt()

        user_states[user_id] = {
            "level": "contact_done",
            "department": department_key
        }

        return build_department_answer(sheet_api, department_key)

    if level == "contact_cskv":
        answer = find_cskv_by_tdp(sheet_api, question)

        if answer:
            user_states[user_id] = {
                "level": "contact_done",
                "department": "CSKV"
            }
            return answer

        return (
            "Xin lỗi, hiện hệ thống chưa tìm thấy nội dung phù hợp. "
            "Quý công dân vui lòng nhập rõ hơn nội dung cần hỏi hoặc nhập 'menu' "
            "để quay lại danh mục hỗ trợ."
        )

    return None


def is_contact_request(question):
    q = normalize_text(question)

    return (
        "tra cuu lien he" in q
        or "tra cứu liên hệ" in q
        or "lien he" in q
        or "liên hệ" in q
        or "so dien thoai" in q
        or "số điện thoại" in q
    )
