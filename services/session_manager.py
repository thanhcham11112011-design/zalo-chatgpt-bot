import json
from datetime import datetime, timedelta
from config import SESSION_TTL_MINUTES, SHEET_SESSION
from services.sheet_api import ensure_session_sheet

_memory = {}


def _now():
    return datetime.now()


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _expired(ctx):
    updated = _parse_time(ctx.get("updated_at"))
    return bool(updated and _now() - updated > timedelta(minutes=SESSION_TTL_MINUTES))


def get_context(user_id):
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
            if str(row.get("USER_ID", "")).strip() == uid:
                raw = row.get("CONTEXT_JSON", "{}")
                data = json.loads(raw) if raw else {}
                data["updated_at"] = row.get("UPDATED_AT", data.get("updated_at", ""))
                if _expired(data):
                    return {}
                _memory[uid] = data
                return dict(data)
    except Exception as e:
        print(f"[SESSION READ ERROR] {e}")
    return {}


def save_context(user_id, context):
    uid = str(user_id or "").strip()
    if not uid:
        return False
    ctx = dict(context or {})
    ctx["updated_at"] = _now().isoformat(timespec="seconds")
    _memory[uid] = ctx
    try:
        ws = ensure_session_sheet()
        values = ws.get_all_values()
        if not values:
            ws.append_row(["USER_ID", "CONTEXT_JSON", "UPDATED_AT"])
            values = ws.get_all_values()
        payload = json.dumps(ctx, ensure_ascii=False)
        for idx, row in enumerate(values[1:], start=2):
            if row and str(row[0]).strip() == uid:
                ws.update(f"A{idx}:C{idx}", [[uid, payload, ctx["updated_at"]]])
                return True
        ws.append_row([uid, payload, ctx["updated_at"]])
        return True
    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")
        return False


def clear_context(user_id):
    uid = str(user_id or "").strip()
    _memory.pop(uid, None)
    save_context(uid, {})
