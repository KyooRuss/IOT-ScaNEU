"""Socket.IO handlers for the guard's live view."""
from ..extensions import socketio
from . import service


@socketio.on("guard_decision")
def on_guard_decision(data):
    """{"log_id": 12, "action": "open" | "deny"} -> ack {"ok": bool, "error"?: str}"""
    data = data or {}
    try:
        log_id = int(data.get("log_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Missing log id."}
    try:
        service.resolve_pending(log_id, data.get("action"))
    except service.GateError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}
