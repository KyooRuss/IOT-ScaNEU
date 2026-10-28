"""Gate simulator: stands in for the cameras, RFID readers and Arduinos during development.

Registered only when SCANEU_SIMULATOR=1. It calls the same gate service the
real hardware will, so everything the dashboard shows is the real pipeline.
"""
from dataclasses import asdict

from flask import Blueprint, jsonify, render_template, request

from ..db import get_db
from ..gate import service

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
    log_id, decision = service.handle_vehicle(lane, rfid_uid=data.get("rfid_uid"), plate_text=plate)
    return jsonify(log_id=log_id, decision=asdict(decision))


@bp.post("/simulator/ir")
def ir():
    data = request.get_json(silent=True) or {}
    lane = _lane(data)
    if lane is None:
        return jsonify(error="Unknown lane."), 400
    service.controller().set_vehicle_present(lane, bool(data.get("present")))
    return jsonify(ok=True)


@bp.post("/simulator/button")
def button():
    """The manual override button on the Arduino: opens the barrier without the Pi deciding."""
    data = request.get_json(silent=True) or {}
    lane = _lane(data)
    if lane is None:
        return jsonify(error="Unknown lane."), 400
    service.controller().open(lane)
    return jsonify(ok=True)
