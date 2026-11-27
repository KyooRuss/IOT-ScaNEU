"""Prints the messages between the Pi and the Arduinos to the terminal.

The Arduinos are not connected yet. Until they are, the simulator (dev/routes.py)
and MockGateController (controller.py) call these functions at the exact places
where the real serial link will receive or send each message, using the protocol
in the README. Each line ends with that place in the code:

    14:02:11  entrance  Arduino -> Pi  UID:04A1B2C3   card tapped                          dev/routes.py:50
    14:02:11  entrance  Pi -> Arduino  OPEN           lift barrier, green LED, short beep  gate/controller.py:48

Set SCANEU_ARDUINO_LOG=0 in .env to turn it off.
"""
import logging
from pathlib import Path

log = logging.getLogger("scaneu.arduino")


def from_arduino(lane, message, meaning):
    """A line the Arduino will send to the Pi, e.g. "UID:04A1B2C3"."""
    _line(lane, "Arduino -> Pi", message, meaning)


def to_arduino(lane, message, meaning):
    """A line the Pi will send to the Arduino, e.g. "OPEN"."""
    _line(lane, "Pi -> Arduino", message, meaning)


def from_camera(lane, plate):
    """The plate the Pi's camera read. Not an Arduino message; shown so the order is clear."""
    _line(lane, "Camera -> Pi", plate or "(none)", "plate read" if plate else "plate unreadable")


def _line(lane, direction, message, meaning):
    # stacklevel=3 records the caller of from_arduino / to_arduino / from_camera, not this file.
    log.info("%-8s  %-13s  %-13s  %-35s", lane, direction, message, meaning, stacklevel=3)


class _Formatter(logging.Formatter):
    def format(self, record):
        record.where = f"{Path(record.pathname).parent.name}/{record.filename}:{record.lineno}"
        return super().format(record)


def init_app(app):
    log.setLevel(logging.INFO if app.config["ARDUINO_LOG"] else logging.WARNING)
    if not log.handlers:  # create_app runs more than once in the tests
        handler = logging.StreamHandler()
        handler.setFormatter(_Formatter("%(asctime)s  %(message)s  %(where)s", "%H:%M:%S"))
        log.addHandler(handler)
        log.propagate = False  # keep these lines out of any other log setup
