"""Runs one gate event end to end: look up the card and plate, apply the access
rules, write the log, move the barrier and push the result to the dashboard.

The simulator calls these functions today; the Arduino serial reader will call
the same ones on the Pi.
"""
from datetime import date, datetime

from flask import current_app

from ..db import get_db, now
from ..extensions import socketio
from ..plates import normalize_plate
from .access_rules import DENIED, GRANTED_BY_GUARD, NON_NEU, PENDING, Card, decide_entrance, decide_exit

LANES = ("entrance", "exit")

LOG_SELECT = """
    SELECT l.*, COALESCE(l.time_out, l.time_in) AS last_activity
    FROM vehicle_logs l
"""

# Finished records the guard should check later (the doc's "review the photo later" /
# "flagged for review" cases). "denied" comes from access_result, the rest from flags.
ALERT_LABELS = {
    "plate_unreadable": "Plate unreadable",
    "exit_only": "Exit without entry",
    "card_expired": "Expired card",
    "card_blocked": "Blocked card",
    "denied": "Denied by guard",
}
ALERT_SQL = "l.pending_lane IS NULL AND (l.access_result = 'Denied' OR {})".format(
    " OR ".join(f"(',' || l.flags || ',') LIKE '%,{flag},%'" for flag in ALERT_LABELS if flag != "denied")
)


class GateError(Exception):
    """A gate request that cannot be carried out; the message is shown to the guard."""


def controller():
    return current_app.extensions["gate_controller"]


def handle_vehicle(lane, rfid_uid=None, plate_text=None, image_path=None):
    """A vehicle at a lane: the card UID tapped (if any) and the plate the camera read (if any)."""
    if lane not in LANES:
        raise GateError(f"Unknown lane '{lane}'.")
    rfid_uid = (rfid_uid or "").strip().upper() or None
    plate = normalize_plate(plate_text)

    db = get_db()
    card = _load_card(db, rfid_uid) if rfid_uid else None
    if lane == "entrance":
        log_id, decision = _entrance(db, card, rfid_uid, plate, image_path)
    else:
        log_id, decision = _exit(db, card, rfid_uid, plate, image_path)
    db.commit()

    if decision.open_barrier:
        controller().open(lane)
    else:
        controller().hold(lane)
    _publish(db, log_id, lane, decision.reason)
    return log_id, decision


def resolve_pending(log_id, action):
    """Guard's Open / Deny on a vehicle waiting at a lane."""
    if action not in ("open", "deny"):
        raise GateError(f"Unknown action '{action}'.")
    db = get_db()
    row = db.execute("SELECT * FROM vehicle_logs WHERE id = ?", (log_id,)).fetchone()
    if row is None or row["pending_lane"] is None:
        raise GateError("This vehicle is no longer waiting.")
    lane = row["pending_lane"]

    if lane == "entrance":
        if action == "open":
            non_neu_id = row["non_neu_vehicle_id"]
            if row["owner_type"] == NON_NEU and row["plate_read"]:
                non_neu_id = _register_non_neu_visit(db, row)
            db.execute(
                "UPDATE vehicle_logs SET access_result = ?, non_neu_vehicle_id = ?, pending_lane = NULL WHERE id = ?",
                (GRANTED_BY_GUARD, non_neu_id, log_id),
            )
        else:
            db.execute(
                "UPDATE vehicle_logs SET access_result = ?, pending_lane = NULL WHERE id = ?", (DENIED, log_id)
            )
    else:
        # An exit-only record is still Pending; an open entry keeps its original result.
        new_result = GRANTED_BY_GUARD if action == "open" else DENIED
        result_sql = "access_result = CASE WHEN access_result = ? THEN ? ELSE access_result END"
        if action == "open":
            time_out = now()
            db.execute(
                f"UPDATE vehicle_logs SET time_out = ?, stay_duration_s = ?, pending_lane = NULL, {result_sql}"
                " WHERE id = ?",
                (time_out, _duration(row["time_in"], time_out), PENDING, new_result, log_id),
            )
        else:
            # The vehicle stays inside; its entry record stays open.
            db.execute(
                f"UPDATE vehicle_logs SET pending_lane = NULL, {result_sql} WHERE id = ?",
                (PENDING, new_result, log_id),
            )

    db.execute(
        "INSERT INTO guard_actions (log_id, action, created_at) VALUES (?, ?, ?)",
        (log_id, action, now()),
    )
    db.commit()

    if action == "open":
        controller().open(lane)
    _publish(db, log_id, lane, "Opened by guard." if action == "open" else "Denied by guard.")


def pending_logs():
    return [log_payload(r) for r in get_db().execute(
        LOG_SELECT + " WHERE l.pending_lane IS NOT NULL ORDER BY l.id"
    )]


def recent_logs(limit=20):
    return [log_payload(r) for r in get_db().execute(
        LOG_SELECT + " ORDER BY last_activity DESC, l.id DESC LIMIT ?", (limit,)
    )]


def alert_logs(reviewed=False):
    return [log_payload(r) for r in get_db().execute(
        LOG_SELECT + f" WHERE {ALERT_SQL} AND l.reviewed_at IS {'NOT ' if reviewed else ''}NULL"
        " ORDER BY last_activity DESC, l.id DESC LIMIT 200"
    )]


def alert_count():
    return get_db().execute(
        f"SELECT COUNT(*) FROM vehicle_logs l WHERE {ALERT_SQL} AND l.reviewed_at IS NULL"
    ).fetchone()[0]


def review_alert(log_id):
    """Guard's "Mark as reviewed" on an alert."""
    db = get_db()
    row = db.execute(LOG_SELECT + " WHERE l.id = ?", (log_id,)).fetchone()
    if row is None or not log_payload(row)["alert_reasons"]:
        raise GateError("This record has no alert to review.")
    if row["reviewed_at"] is None:
        db.execute("UPDATE vehicle_logs SET reviewed_at = ? WHERE id = ?", (now(), log_id))
        db.commit()
        row = db.execute(LOG_SELECT + " WHERE l.id = ?", (log_id,)).fetchone()
    socketio.emit("alert_update", {"log": log_payload(row), "alert_count": alert_count()})
    return log_payload(row)


def review_all_alerts():
    """Guard's "Mark all as reviewed". Returns how many alerts were marked."""
    db = get_db()
    cur = db.execute(
        "UPDATE vehicle_logs SET reviewed_at = ? WHERE id IN"
        f" (SELECT l.id FROM vehicle_logs l WHERE {ALERT_SQL} AND l.reviewed_at IS NULL)",
        (now(),),
    )
    db.commit()
    socketio.emit("alert_update", {"log": None, "all_reviewed": True, "alert_count": alert_count()})
    return cur.rowcount


def log_payload(row):
    data = dict(row)
    data["flags"] = [f for f in data["flags"].split(",") if f]
    data["alert_reasons"] = _alert_reasons(data)
    return data


def _alert_reasons(data):
    if data["pending_lane"]:
        return []  # still waiting: the guard decides on Live Log first
    reasons = [f for f in data["flags"] if f in ALERT_LABELS]
    if data["access_result"] == DENIED:
        reasons.append("denied")
    return reasons


def _entrance(db, card, rfid_uid, plate, image_path):
    non_neu = (
        db.execute("SELECT * FROM non_neu_vehicles WHERE plate_number = ?", (plate,)).fetchone() if plate else None
    )
    decision = decide_entrance(
        card=card, card_tapped=rfid_uid is not None, plate=plate,
        known_non_neu=non_neu is not None, today=date.today(),
    )
    vehicle_type, vehicle_color = _vehicle_info(db, decision.plate, non_neu)
    cur = db.execute(
        """INSERT INTO vehicle_logs (plate_read, owner_type, user_id, non_neu_vehicle_id, rfid_uid,
               access_result, time_in, vehicle_type, vehicle_color, entry_image_path, flags, pending_lane)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            decision.plate, decision.owner_type, card.user_id if card else None,
            non_neu["id"] if non_neu and decision.owner_type == NON_NEU else None,
            rfid_uid, decision.access_result, now(), vehicle_type, vehicle_color, image_path,
            ",".join(decision.flags), None if decision.open_barrier else "entrance",
        ),
    )
    return cur.lastrowid, decision


def _exit(db, card, rfid_uid, plate, image_path):
    entry = _find_open_entry(db, card, plate)
    decision = decide_exit(
        card=card, plate=plate, open_entry_owner=entry["owner_type"] if entry else None, today=date.today()
    )
    if entry is not None:
        if decision.open_barrier:
            time_out = now()
            db.execute(
                "UPDATE vehicle_logs SET time_out = ?, stay_duration_s = ?, exit_image_path = ? WHERE id = ?",
                (time_out, _duration(entry["time_in"], time_out), image_path, entry["id"]),
            )
        else:
            db.execute(
                "UPDATE vehicle_logs SET pending_lane = 'exit', exit_image_path = ? WHERE id = ?",
                (image_path, entry["id"]),
            )
        return entry["id"], decision

    cur = db.execute(
        """INSERT INTO vehicle_logs (plate_read, owner_type, user_id, rfid_uid, access_result,
               exit_image_path, flags, pending_lane)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'exit')""",
        (
            plate, decision.owner_type, card.user_id if card else None, rfid_uid,
            decision.access_result, image_path, ",".join(decision.flags),
        ),
    )
    return cur.lastrowid, decision


def _load_card(db, rfid_uid):
    user = db.execute("SELECT * FROM users WHERE rfid_uid = ?", (rfid_uid,)).fetchone()
    if user is None:
        return None
    plates = frozenset(
        r["plate_number"] for r in db.execute("SELECT plate_number FROM vehicles WHERE user_id = ?", (user["id"],))
    )
    valid_until = date.fromisoformat(user["valid_until"]) if user["valid_until"] else None
    return Card(user_id=user["id"], status=user["card_status"], valid_until=valid_until, plates=plates)


def _find_open_entry(db, card, plate):
    """Latest granted entry with no time_out, matched by card holder first, then by plate."""
    open_sql = (
        "SELECT * FROM vehicle_logs WHERE time_in IS NOT NULL AND time_out IS NULL"
        " AND access_result IN ('Granted', 'Granted by guard') AND {} = ? ORDER BY time_in DESC LIMIT 1"
    )
    if card is not None:
        row = db.execute(open_sql.format("user_id"), (card.user_id,)).fetchone()
        if row is not None:
            return row
    if plate is not None:
        return db.execute(open_sql.format("plate_read"), (plate,)).fetchone()
    return None


def _vehicle_info(db, plate, non_neu):
    """Type and color from the registry until the AI detects them from the camera."""
    if non_neu is not None:
        return non_neu["vehicle_type"], non_neu["vehicle_color"]
    if plate:
        row = db.execute(
            "SELECT vehicle_type, vehicle_color FROM vehicles WHERE plate_number = ?", (plate,)
        ).fetchone()
        if row is not None:
            return row["vehicle_type"], row["vehicle_color"]
    return None, None


def _register_non_neu_visit(db, log_row):
    """Every visitor plate let in is kept on record; returning plates get their visit count bumped."""
    seen = now()
    db.execute(
        """INSERT INTO non_neu_vehicles (plate_number, vehicle_type, vehicle_color, first_seen, last_seen, visit_count)
           VALUES (?, ?, ?, ?, ?, 1)
           ON CONFLICT (plate_number) DO UPDATE SET last_seen = excluded.last_seen, visit_count = visit_count + 1""",
        (log_row["plate_read"], log_row["vehicle_type"], log_row["vehicle_color"], seen, seen),
    )
    return db.execute(
        "SELECT id FROM non_neu_vehicles WHERE plate_number = ?", (log_row["plate_read"],)
    ).fetchone()["id"]


def _duration(time_in, time_out):
    if not time_in:
        return None
    return int((datetime.fromisoformat(time_out) - datetime.fromisoformat(time_in)).total_seconds())


def pending_count():
    return get_db().execute("SELECT COUNT(*) FROM vehicle_logs WHERE pending_lane IS NOT NULL").fetchone()[0]


def last_events():
    """Latest gate event per lane, kept in memory for the Live Log camera cards."""
    return current_app.extensions.setdefault("last_gate_events", {})


def _publish(db, log_id, lane, reason):
    row = db.execute(LOG_SELECT + " WHERE l.id = ?", (log_id,)).fetchone()
    event = {
        "lane": lane, "reason": reason, "at": now(), "log": log_payload(row),
        "pending_count": pending_count(), "alert_count": alert_count(),
    }
    last_events()[lane] = event
    socketio.emit("gate_event", event)
