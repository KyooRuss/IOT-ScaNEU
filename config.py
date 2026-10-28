"""Settings for the ScaNEU dashboard.

Every value can be overridden in a `.env` file (see `.env.example`), so the
same code runs on a Windows laptop and on the Raspberry Pi.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _flag(name, default):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SCANEU_SECRET_KEY", "dev-only-change-me")
    DATABASE = os.environ.get("SCANEU_DATABASE", str(BASE_DIR / "instance" / "scaneu.db"))
    IMAGE_DIR = os.environ.get("SCANEU_IMAGE_DIR", str(BASE_DIR / "data" / "images"))

    HOST = os.environ.get("SCANEU_HOST", "127.0.0.1")
    PORT = int(os.environ.get("SCANEU_PORT", "5000"))
    DEBUG = _flag("SCANEU_DEBUG", "0")

    # Mock gate + /dev/simulator page. Turn off on the Pi once the Arduinos are wired.
    SIMULATOR = _flag("SCANEU_SIMULATOR", "1")

    # Safety rules from the doc: close 3 s after the IR sensor is clear.
    BARRIER_CLOSE_DELAY = float(os.environ.get("SCANEU_BARRIER_CLOSE_DELAY", "3"))
    # Close an opened barrier if no vehicle ever crosses the IR sensor.
    BARRIER_OPEN_TIMEOUT = float(os.environ.get("SCANEU_BARRIER_OPEN_TIMEOUT", "15"))
