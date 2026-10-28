"""Visitor plates. Read-only list for now.

Card holders are managed by the school, not the guard, so the dashboard has no page for them.
"""
from flask import Blueprint, render_template

from ..db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/visitors")
def visitors():
    rows = get_db().execute("SELECT * FROM non_neu_vehicles ORDER BY last_seen DESC").fetchall()
    return render_template("admin/visitors.html", visitors=rows)
