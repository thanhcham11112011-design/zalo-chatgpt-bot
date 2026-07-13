import json
from datetime import datetime
from typing import Any, Dict

from services.sheet_api import (
    ensure_session_sheet,
    read_session,
    save_session,
)

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
# Vai trò: Ưu tiên bộ nhớ tạm và chỉ đọc BOT_SESSION khi chưa có cache.
def get_context(user_id: Any) -> Dict[str, Any]:
    uid = _uid(user_id)
    if not uid:
        return {}

    if uid in _memory:
        return dict(_memory[uid])

    try:
        stored_context = _safe_context(read_session(uid))

        if not stored_context:
            _memory[uid] = {}
            return {}

        ctx = _normalize_context(stored_context)
        _memory[uid] = ctx
        return dict(ctx)

    except Exception as e:
        print(f"[SESSION READ ERROR] {e}")
        _memory[uid] = {}
        return {}


# Chức năng: Lưu context hội thoại của một người dùng.
# Vai trò: Cập nhật cache và chỉ đồng bộ BOT_SESSION khi ngữ cảnh kỹ thuật thay đổi.
def save_context(user_id: Any, context: Dict[str, Any]) -> bool:
    uid = _uid(user_id)
    if not uid:
        return False

    previous_context = _safe_context(_memory.get(uid))
    ctx = _normalize_context(_safe_context(context))
    updated_at = _now().isoformat(timespec="seconds")
    ctx["updated_at"] = updated_at
    _memory[uid] = ctx

    tracked_keys = (
        "sheet",
        "topic",
        "procedure_id",
        "procedure_name",
        "stage",
        "page",
        "last_suggestions",
    )

    context_changed = any(
        previous_context.get(key) != ctx.get(key)
        for key in tracked_keys
    )

    if not context_changed:
        return True

    try:
        return save_session(
            user_id=uid,
            context=ctx,
            updated_at=updated_at,
        )

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

    try:
        ws = ensure_session_sheet()
        values = ws.get_all_values()
        row_index = _find_user_row(values, uid)

        if row_index:
            ws.delete_rows(row_index)

        return True

    except Exception as e:
        print(f"[SESSION CLEAR ERROR] {e}")
        return False
