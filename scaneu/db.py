"""SQLite access (one connection per request) and the database CLI commands."""
import sqlite3
from datetime import datetime
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext

SCHEMA = Path(__file__).with_name("schema.sql")

# Children first, so DROP works with foreign keys on.
TABLES = (
    "guard_actions",
    "visit_details",
    "vehicle_logs",
    "non_neu_vehicles",
    "vehicles",
    "users",
)


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now():
    """Current local time in the format stored in the database."""
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


# Columns added to schema.sql after a table first shipped. CREATE TABLE IF NOT EXISTS
# skips existing tables, so init_schema adds these to older databases without losing data.
ADDED_COLUMNS = [
    ("vehicle_logs", "reviewed_at", "TEXT"),
]


def init_schema(conn, reset=False):
    if reset:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
    # WAL lets the gate and the dashboard write at the same time; it is stored in the file.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    for table, column, definition in ADDED_COLUMNS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()


# Demo data for development. Card UIDs are what the RC522 reader sends (hex, upper-case).
DEMO_USERS = [
    # full name, NEU ID, RFID UID, card status, valid until, [(plate, type, color)]
    ("Maria Santos", "21-10001-001", "04A1B2C3", "Active", "2027-06-30", [("ABC1234", "Sedan", "White")]),
    ("Juan Dela Cruz", "19-10002-002", "04D4E5F6", "Active", "2025-06-30", [("NEU5678", "SUV", "Black")]),
    ("Ana Reyes", "22-10003-003", "0477889A", "Blocked", "2027-06-30", [("XYZ9012", "Motorcycle", "Red")]),
]
DEMO_NON_NEU = [
    # plate, type, color, driver, ID type, visits
    ("VIS4321", "Van", "Silver", "Pedro Lim", "Driver's license", 2),
]


def seed_demo(conn):
    for name, neu_id, uid, status, valid_until, plates in DEMO_USERS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO users (full_name, neu_id, rfid_uid, card_status, valid_until)"
            " VALUES (?, ?, ?, ?, ?)",
            (name, neu_id, uid, status, valid_until),
        )
        if cur.rowcount:
            for plate, vtype, color in plates:
                conn.execute(
                    "INSERT OR IGNORE INTO vehicles (plate_number, user_id, vehicle_type, vehicle_color)"
                    " VALUES (?, ?, ?, ?)",
                    (plate, cur.lastrowid, vtype, color),
                )
    seen = now()
    for plate, vtype, color, driver, id_type, visits in DEMO_NON_NEU:
        conn.execute(
            "INSERT OR IGNORE INTO non_neu_vehicles"
            " (plate_number, vehicle_type, vehicle_color, driver_name, id_type, first_seen, last_seen, visit_count)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (plate, vtype, color, driver, id_type, seen, seen, visits),
        )
    conn.commit()


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Drop every table first. Deletes all data.")
@with_appcontext
def init_db_command(reset):
    """Create the database tables (safe to run again)."""
    if reset:
        click.confirm("This deletes ALL ScaNEU data. Continue?", abort=True)
    init_schema(get_db(), reset=reset)
    click.echo(f"Database ready: {current_app.config['DATABASE']}")


@click.command("seed-demo")
@with_appcontext
def seed_demo_command():
    """Add demo cards and plates for development."""
    conn = get_db()
    init_schema(conn)
    seed_demo(conn)
    click.echo("Demo cards and plates added.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
