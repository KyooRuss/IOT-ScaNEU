"""Start the ScaNEU dashboard: python run.py"""
from scaneu import create_app
from scaneu.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # Werkzeug's threaded server is fine for a single gate on the LAN.
    socketio.run(
        app,
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
        allow_unsafe_werkzeug=True,
    )
