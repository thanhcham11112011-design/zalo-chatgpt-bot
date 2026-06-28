import re


CONTACT_SHEET = "TRA_CUU_LIEN_HE"


def normalize_text(text):
    text = str(text or "").lower().strip()
    text = text.replace("đ", "d")
    text = re.sub(r"\s+", " ", text)
    return text


CONTACT_MENU = [
    {"key": "CHI_HUY", "name": "Liên hệ chỉ huy Công an phường"},
    {"key": "CSKV", "name": "Liên hệ bộ phận CSKV"},
    {"key": "PCTP", "name": "Liên hệ bộ phận PCTP"},
    {"key": "CSTT", "name": "Liên hệ bộ phận CSTT"},
    {"key": "AN", "name": "Liên hệ bộ phận An ninh"},
    {"key": "CNTT", "name": "Liên hệ tổ CNTT"},
    {"key": "DOAN_THANH_NIEN", "name": "Liên hệ đồng chí Bí thư ĐTNCS"},
]


def get_value(row, columns):
    for col in columns:
        value = row.get(col)
        if value:
            return str(value).strip()
    return ""


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
        if normalize_text(item["key"]) in q:
            return item["key"]

        if normalize_text(item["name"]) in q:
            return item["key"]

    return None


def format_contact_row(row):
    ho_ten = get_value(row, ["HỌ_TÊN", "HO_TEN", "TEN"])
    chuc_vu = get_value(row, ["CHỨC_VỤ", "CHUC_VU"])
    dien_thoai = get_value(row, ["ĐIỆN_THOẠI", "DIEN_THOAI", "SDT", "SĐT"])
    email = get_value(row, ["EMAIL"])
    tdp = get_value(row, ["TDP"])
    ghi_chu = get_value(row, ["GHI_CHÚ", "GHI_CHU"])

    lines = []

    if ho_ten:
        lines.append(f"👤 Họ tên: {ho_ten}")
    if chuc_vu:
        lines.append(f"💼 Chức vụ/Bộ phận: {chuc_vu}")
    if tdp:
        lines.append(f"🏘️ Phụ trách: {tdp}")
    if dien_thoai:
        lines.append(f"☎️ Số điện thoại: {dien_thoai}")
    if email:
        lines.append(f"📧 Email: {email}")
    if ghi_chu:
        lines.append(f"📝 Ghi chú: {ghi_chu}")

    return "\n".join(lines)


def find_department_contacts(sheet_api, department_key):
    rows = sheet_api.read_sheet(CONTACT_SHEET)
    results = []

    for row in rows:
        bo_phan = normalize_text(get_value(row, ["BO_PHAN"]))

        if bo_phan == normalize_text(department_key):
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
        "- Tổ 1\n"
        "- Gò Công 1\n"
        "- Trần Phú\n"
        "- Tôi ở Tổ Trần phú\n"
        "- Tôi ở Tổ Gò Công 1"
    )


def find_cskv_by_area(sheet_api, question):
    q = normalize_text(question)
    rows = find_department_contacts(sheet_api, "CSKV")
    results = []

    for row in rows:
        tdp = normalize_text(get_value(row, ["TDP"]))
        tu_khoa = normalize_text(get_value(row, ["TU_KHOA"]))

        search_text = f"{tdp}, {tu_khoa}"

        keywords = [
            normalize_text(x)
            for x in re.split(r"[,;|\n]+", search_text)
            if normalize_text(x)
        ]

        for kw in keywords:
            if kw and kw in q:
                results.append(row)
                break

    if not results:
        return None

    lines = ["👮 CẢNH SÁT KHU VỰC PHỤ TRÁCH\n"]

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

    # ===== MENU TRA CỨU LIÊN HỆ =====
    if level == "contact_menu":
        department_key = get_contact_key_from_question(question)

        if not department_key:
            return (
                "Nội dung nhập chưa phù hợp với danh sách tra cứu liên hệ.\n\n"
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

    # ===== TRA CỨU CSKV =====
    if level == "contact_cskv":
        answer = find_cskv_by_area(sheet_api, question)

        if answer:
            user_states[user_id] = {
                "level": "contact_cskv",
                "department": "CSKV"
            }

            return (
                answer
                + "\n\n💡 Quý công dân có thể tiếp tục nhập tên TDP hoặc khu dân cư khác để tra cứu Cảnh sát khu vực phụ trách."
                + "\nHoặc nhập 'menu' để quay lại danh mục hỗ trợ."
            )

        return (
            "Xin lỗi, hiện hệ thống chưa tìm thấy nội dung phù hợp.\n\n"
            "Quý công dân vui lòng nhập đúng tên TDP hoặc khu dân cư cần tra cứu "
            "(ví dụ: Trần Phú, Gò Công 1, Nam Hải, Tổ 6...).\n"
            "Hoặc nhập 'menu' để quay lại danh mục hỗ trợ."
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
