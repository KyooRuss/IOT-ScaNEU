"""ScaNEU dashboard: Flask app factory."""
from pathlib import Path

from flask import Flask, redirect, url_for

from config import BASE_DIR, Config

from . import db
from .extensions import csrf, socketio
from .gate import events  # noqa: F401  Socket.IO handlers must be registered before socketio.init_app()
from .gate.access_rules import FLAG_LABELS
from .gate.controller import MockGateController
from .gate.service import LANES, alert_count, pending_count
from .plates import format_plate


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["IMAGE_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)

    # The Arduino serial controller will replace this on the Pi.
    app.extensions["gate_controller"] = MockGateController(
        socketio,
        LANES,
        close_delay=app.config["BARRIER_CLOSE_DELAY"],
        open_timeout=app.config["BARRIER_OPEN_TIMEOUT"],
    )

    from .admin.routes import bp as admin_bp
    from .guard.routes import bp as guard_bp
    from .logs.routes import bp as logs_bp

    app.register_blueprint(guard_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(admin_bp)

    if app.config["SIMULATOR"]:
        from .dev.routes import bp as dev_bp

        app.register_blueprint(dev_bp)

    app.jinja_env.globals["FLAG_LABELS"] = FLAG_LABELS
    app.jinja_env.filters["plate"] = format_plate

    @app.context_processor
    def sidebar_counts():
        return {"pending_count": pending_count(), "alert_count": alert_count()}

    @app.get("/")
    def index():
        return redirect(url_for("guard.live"))

    return app
