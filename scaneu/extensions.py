"""Flask extensions, created here and bound to the app in create_app()."""
from flask_socketio import SocketIO
from flask_wtf import CSRFProtect

# "threading" needs no eventlet/gevent, so it runs the same on Windows and the Pi.
socketio = SocketIO(async_mode="threading")
csrf = CSRFProtect()
