from flask import Blueprint, render_template, request

from ..db import get_db
from ..gate.service import LOG_SELECT, log_payload
from ..plates import normalize_plate

bp = Blueprint("logs", __name__)


@bp.get("/logs")
def index():
    plate = normalize_plate(request.args.get("plate"))
    sql, params = LOG_SELECT, []
    if plate:
        sql += " WHERE l.plate_read LIKE ?"
        params.append(f"%{plate}%")
    sql += " ORDER BY last_activity DESC, l.id DESC LIMIT 200"
    logs = [log_payload(r) for r in get_db().execute(sql, params)]
    return render_template("logs/index.html", logs=logs, plate=plate or "")
