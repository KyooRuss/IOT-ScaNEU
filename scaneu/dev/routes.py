"""Gate simulator: stands in for the cameras, RFID readers and Arduinos during development.

Registered only when SCANEU_SIMULATOR=1. It calls the same gate service the
real hardware will, so everything the dashboard shows is the real pipeline.
Each route prints the serial message the real Arduino will send for that action
(UID, IR, BTN); the serial reader on the Pi will replace these routes.
"""
from dataclasses import asdict

from flask import Blueprint, jsonify, render_template, request

from ..db import get_db
from ..gate import serial_log, service

bp = Blueprint("dev", __name__, url_prefix="/dev")


def _lane(data):
    lane = data.get("lane")
    if lane not in service.LANES:
        return None
    return lane


@bp.get("/simulator")
def simulator():
    db = get_db()
    users = db.execute(
        "SELECT full_name, rfid_uid, card_status, valid_until FROM users"
        " WHERE rfid_uid IS NOT NULL ORDER BY full_name"
    ).fetchall()
    plates = [r[0] for r in db.execute(
        "SELECT plate_number FROM vehicles UNION SELECT plate_number FROM non_neu_vehicles ORDER BY 1"
    )]
    return render_template(
        "dev/simulator.html", users=users, plates=plates, lanes=service.LANES,
        barriers=service.controller().snapshot(),
    )


@bp.post("/simulator/vehicle")
def vehicle():
    data = request.get_json(silent=True) or {}
    lane = _lane(data)
    if lane is None:
        return jsonify(error="Unknown lane."), 400
    plate = None if data.get("plate_unreadable") else data.get("plate")
    rfid_uid = (data.get("rfid_uid") or "").strip()
    if rfid_uid:  # no card tapped: the Arduino sends nothing
        serial_log.from_arduino(lane, f"UID:{rfid_uid}", "card tapped")
    serial_log.from_camera(lane, (plate or "").strip())
    log_id, decision = service.handle_vehicle(lane, rfid_uid=rfid_uid, plate_text=plate)
    return jsonify(log_id=log_id, decision=asdict(decision))


@bp.post("/simulator/ir")
def ir():
    data = request.get_json(silent=True) or {}
    lane = _lane(data)
    if lane is None:
        return jsonify(error="Unknown lane."), 400
    present = bool(data.get("present"))
    if present:
        serial_log.from_arduino(lane, "IR:1", "vehicle under barrier")
    else:
        serial_log.from_arduino(lane, "IR:0", "barrier clear")
    service.controller().set_vehicle_present(lane, present)
    return jsonify(ok=True)


@bp.post("/simulator/button")
def button():
    """The manual override button on the Arduino: opens the barrier without the Pi deciding."""
    data = request.get_json(silent=True) or {}
    lane = _lane(data)
    if lane is None:
        return jsonify(error="Unknown lane."), 400
    serial_log.from_arduino(lane, "BTN", "manual button pressed")
    service.controller().open(lane)
    return jsonify(ok=True)
