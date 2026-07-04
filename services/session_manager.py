import json
from datetime import datetime, timedelta

from config import SESSION_TTL_MINUTES, SHEET_SESSION
from services.sheet_api import ensure_session_sheet

_memory = {}


# Chức năng: Lấy thời điểm hiện tại của hệ thống.
# Vai trò: Thống nhất thời gian sử dụng trong toàn bộ Session Manager.
def _now():
    return datetime.now()


# Chức năng: Chuyển chuỗi thời gian ISO sang đối tượng datetime.
# Vai trò: Chuẩn hóa thời gian đọc từ Google Sheets và bộ nhớ.
def _parse_time(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).strip())
    except Exception:
        return None


# Chức năng: Kiểm tra Session đã hết hạn hay chưa.
# Vai trò: Tự động loại bỏ Session quá thời gian cấu hình trong BOT.
def _expired(ctx):
    if not isinstance(ctx, dict):
        return True

    updated = _parse_time(ctx.get("updated_at"))

    if updated is None:
        return False

    return (_now() - updated) > timedelta(minutes=SESSION_TTL_MINUTES)

def get_context(user_id):
    # Chức năng: Lấy ngữ cảnh hội thoại của một người dùng.
    # Vai trò: Ưu tiên đọc từ RAM, sau đó đọc từ BOT_SESSION trong Google Sheets.
    uid = str(user_id or "").strip()
    if not uid:
        return {}

    ctx = _memory.get(uid)

    if ctx and not _expired(ctx):
        return dict(ctx)

    if ctx and _expired(ctx):
        _memory.pop(uid, None)
        return {}

    try:
        ws = ensure_session_sheet()
        rows = ws.get_all_records()

        for row in rows:
            if str(row.get("USER_ID", "")).strip() != uid:
                continue

            raw = row.get("CONTEXT_JSON", "{}")

            try:
                data = json.loads(raw) if raw else {}
            except Exception:
                data = {}

            if not isinstance(data, dict):
                data = {}

            data["updated_at"] = row.get("UPDATED_AT", data.get("updated_at", ""))

            if _expired(data):
                _memory.pop(uid, None)
                return {}

            _memory[uid] = data
            return dict(data)

    except Exception as e:
        print(f"[SESSION READ ERROR] {e}")

    return {}

# Chức năng: Lưu ngữ cảnh hội thoại của người dùng.
# Vai trò: Đồng bộ Session giữa RAM và Google Sheets để BOT duy trì hội thoại.
def save_context(user_id, context):
    uid = str(user_id or "").strip()

    if not uid:
        return False

    ctx = dict(context or {})
    ctx["updated_at"] = _now().isoformat(timespec="seconds")

    _memory[uid] = dict(ctx)

    try:
        ws = ensure_session_sheet()

        values = ws.get_all_values()

        if not values:
            ws.append_row([
                "USER_ID",
                "CONTEXT_JSON",
                "UPDATED_AT",
            ])
            values = ws.get_all_values()

        payload = json.dumps(
            ctx,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        for idx, row in enumerate(values[1:], start=2):
            if row and str(row[0]).strip() == uid:
                ws.update(
                    f"A{idx}:C{idx}",
                    [[uid, payload, ctx["updated_at"]]],
                )
                return True

        ws.append_row([
            uid,
            payload,
            ctx["updated_at"],
        ])

        return True

    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")
        return False


# Chức năng: Xóa ngữ cảnh hội thoại của người dùng.
# Vai trò: Kết thúc hội thoại hoặc reset BOT về trạng thái ban đầu.
def clear_context(user_id):
    uid = str(user_id or "").strip()

    if not uid:
        return False

    _memory.pop(uid, None)

    return save_context(uid, {})

