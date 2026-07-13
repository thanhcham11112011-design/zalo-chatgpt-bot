import json
from datetime import datetime
from typing import Any, Dict

from services.sheet_api import ensure_session_sheet

_memory: Dict[str, Dict[str, Any]] = {}


# Chức năng: Lấy thời điểm hiện tại theo định dạng hệ thống.
# Vai trò: Phục vụ kiểm tra hạn phiên và cập nhật thời gian session.
def _now() -> datetime:
    return datetime.now()


# Chức năng: Chuẩn hóa khóa người dùng trước khi lưu hoặc đọc session.
# Vai trò: Tránh lỗi do user_id rỗng, None hoặc có khoảng trắng.
def _uid(user_id: Any) -> str:
    return str(user_id or "").strip()


# Chức năng: Bảo đảm context là dict hợp lệ.
# Vai trò: Ngăn lỗi khi dữ liệu session từ Google Sheets bị rỗng hoặc sai định dạng.
def _safe_context(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


# Chức năng: Chuyển context thành JSON để ghi vào BOT_SESSION.
# Vai trò: Lưu ngữ cảnh kỹ thuật mà không đưa nghiệp vụ vào code.
def _context_json(context: Dict[str, Any]) -> str:
    return json.dumps(context or {}, ensure_ascii=False)


# Chức năng: Đọc JSON context từ BOT_SESSION.
# Vai trò: Khôi phục ngữ cảnh hội thoại theo từng người dùng.
def _load_context_json(raw: Any) -> Dict[str, Any]:
    try:
        data = json.loads(str(raw or "{}").strip() or "{}")
        return _safe_context(data)
    except Exception:
        return {}


# Chức năng: Tìm số dòng của một USER_ID trong sheet BOT_SESSION.
# Vai trò: Hỗ trợ cập nhật đúng dòng session thay vì tạo trùng lặp.
def _find_user_row(values, user_id: str) -> int:
    for idx, row in enumerate(values[1:], start=2):
        if row and str(row[0]).strip() == user_id:
            return idx
    return 0


# Chức năng: Chuẩn hóa context trước khi ghi cache và Google Sheets.
# Vai trò: Bảo đảm BOT_SESSION chỉ lưu trạng thái kỹ thuật cần thiết của phiên chat.
def _normalize_context(context: Dict[str, Any]) -> Dict[str, Any]:
    ctx = dict(context or {})
    allowed_defaults = {
        "last_route": "",
        "sheet": "",
        "topic": "",
        "procedure_id": "",
        "procedure_name": "",
        "stage": "",
        "page": 1,
        "last_suggestions": [],
    }
    for key, default in allowed_defaults.items():
        ctx.setdefault(key, default)
    return ctx


# Chức năng: Đọc context hội thoại của một người dùng.
# Vai trò: Cung cấp ngữ cảnh kỹ thuật cho router xử lý câu hỏi nối tiếp.
def get_context(user_id: Any) -> Dict[str, Any]:
    uid = _uid(user_id)
    if not uid:
        return {}

    cached = _memory.get(uid)
    if cached:
        return dict(cached)

    try:
        ws = ensure_session_sheet()
        rows = ws.get_all_records(default_blank="")
        for row in rows:
            if str(row.get("USER_ID", "")).strip() != uid:
                continue

            ctx = _load_context_json(row.get("CONTEXT_JSON", "{}"))
            updated_at = row.get("UPDATED_AT") or row.get("UPDATED_TIME") or ctx.get("updated_at") or ""
            ctx["updated_at"] = str(updated_at or "")

            _memory[uid] = ctx
            return dict(ctx)

    except Exception as e:
        print(f"[SESSION READ ERROR] {e}")

    return {}


# Chức năng: Lưu context hội thoại của một người dùng.
# Vai trò: Ghi ngữ cảnh kỹ thuật vào bộ nhớ tạm và sheet BOT_SESSION.
def save_context(user_id: Any, context: Dict[str, Any]) -> bool:
    uid = _uid(user_id)
    if not uid:
        return False

    ctx = _normalize_context(_safe_context(context))
    updated_at = _now().isoformat(timespec="seconds")
    ctx["updated_at"] = updated_at
    _memory[uid] = ctx

    try:
        ws = ensure_session_sheet()
        values = ws.get_all_values()
        if not values:
            ws.append_row([
                "USER_ID",
                "CONTEXT_JSON",
                "LAST_ROUTE",
                "LAST_SHEET",
                "LAST_RECORD_ID",
                "LAST_MENU",
                "LAST_PROCEDURE",
                "PAGE",
                "UPDATED_AT",
            ])
            values = ws.get_all_values()

        row_values = [
            uid,
            _context_json(ctx),
            str(ctx.get("last_route", "")),
            str(ctx.get("sheet", "")),
            str(ctx.get("procedure_id", "")),
            str(ctx.get("topic", "")),
            str(ctx.get("procedure_name", "")),
            str(ctx.get("page", "")),
            updated_at,
        ]

        row_index = _find_user_row(values, uid)
        if row_index:
            ws.update(f"A{row_index}:I{row_index}", [row_values])
        else:
            ws.append_row(row_values)
        return True

    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")
        return False


# Chức năng: Xóa context hội thoại của một người dùng.
# Vai trò: Reset phiên chat khi người dân quay lại menu hoặc kết thúc trao đổi.
def clear_context(user_id: Any) -> bool:
    uid = _uid(user_id)
    if not uid:
        return False

    _memory.pop(uid, None)
    return save_context(uid, {})
