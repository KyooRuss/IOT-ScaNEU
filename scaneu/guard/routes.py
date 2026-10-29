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


def _alert_filter():
    """?show=reviewed and ?reason=<alert reason> from the Alerts page."""
    reason = request.args.get("reason")
    return request.args.get("show") == "reviewed", reason if reason in service.ALERT_LABELS else None


@bp.get("/alerts")
def alerts():
    reviewed, reason = _alert_filter()
    counts = service.alert_counts(reviewed)
    state = {**service.alert_page(reviewed, reason), "reviewed": reviewed, "reason": reason, "counts": counts}
    return render_template(
        "guard/alerts.html", state=state, reviewed=reviewed, reason=reason, counts=counts,
        alert_labels=service.ALERT_LABELS,
    )


@bp.get("/alerts/more")
def alerts_more():
    """The next page of the list; offset is how many alerts the page already shows."""
    reviewed, reason = _alert_filter()
    return jsonify(service.alert_page(reviewed, reason, max(request.args.get("offset", 0, type=int), 0)))


@bp.get("/alerts/counts")
def alerts_counts():
    reviewed, _ = _alert_filter()
    return jsonify(service.alert_counts(reviewed))


@bp.post("/alerts/review-all")
def review_all():
    reason = (request.get_json(silent=True) or {}).get("reason")
    if reason is not None and reason not in service.ALERT_LABELS:
        return jsonify(error="Unknown alert reason."), 400
    return jsonify(reviewed=service.review_all_alerts(reason))


@bp.post("/alerts/<int:log_id>/review")
def review(log_id):
    plate = (request.get_json(silent=True) or {}).get("plate")
    try:
        log = service.review_alert(log_id, plate if isinstance(plate, str) else None)
    except service.GateError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(log=log)


@bp.post("/alerts/<int:log_id>/unreview")
def unreview(log_id):
    try:
        log = service.unreview_alert(log_id)
    except service.GateError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(log=log)


@bp.get("/images/<path:filename>")
def image(filename):
    """Vehicle photos saved by the cameras (paths stored in vehicle_logs)."""
    return send_from_directory(current_app.config["IMAGE_DIR"], filename)
