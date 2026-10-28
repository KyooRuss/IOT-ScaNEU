from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory

from ..gate import service

bp = Blueprint("guard", __name__)


@bp.get("/guard")
def live():
    state = {
        "recent": service.recent_logs(),
        "pending": service.pending_logs(),
        "barriers": service.controller().snapshot(),
        "last_events": service.last_events(),
    }
    return render_template("guard/live.html", state=state, lanes=service.LANES)


@bp.get("/alerts")
def alerts():
    reviewed = request.args.get("show") == "reviewed"
    state = {"alerts": service.alert_logs(reviewed=reviewed), "reviewed": reviewed}
    return render_template(
        "guard/alerts.html", state=state, reviewed=reviewed, alert_labels=service.ALERT_LABELS,
    )


@bp.post("/alerts/review-all")
def review_all():
    return jsonify(reviewed=service.review_all_alerts())


@bp.post("/alerts/<int:log_id>/review")
def review(log_id):
    try:
        log = service.review_alert(log_id)
    except service.GateError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(log=log)


@bp.get("/images/<path:filename>")
def image(filename):
    """Vehicle photos saved by the cameras (paths stored in vehicle_logs)."""
    return send_from_directory(current_app.config["IMAGE_DIR"], filename)
