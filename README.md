# ScaNEU: gate dashboard

Vehicle access control for the New Era University gate. A Raspberry Pi 5 runs the access rules, the SQLite database and this Flask dashboard. Two Arduino Unos (entrance and exit lanes) run the RFID readers, barriers, IR sensors, LEDs and buzzers.

This repository currently contains the **dashboard**, with a **mock gate simulator** so it can be built and tested on a laptop without the Pi or Arduinos.

## Tech stack
- Python 3.11+, Flask 3 (app factory + blueprints), Jinja templates
- Flask-SocketIO (threading mode) for live gate events
- Flask-WTF (CSRF protection)
- SQLite (built into Python), WAL mode
- Bootstrap 5.3, Bootstrap Icons and the Socket.IO client, bundled in `scaneu/static/vendor/` so the dashboard works with no internet
- pytest

## Setup (Windows)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # or .venv\Scripts\activate.bat in cmd
pip install -r requirements.txt
copy .env.example .env                 # then set SCANEU_SECRET_KEY to a long random string
flask init-db                          # create the tables
flask seed-demo                        # demo cards and plates
python run.py                          # http://127.0.0.1:5000
```
On Linux / the Pi, use `source .venv/bin/activate` and `cp` instead of `copy`.

## Trying the gate
1. Open **Live Log** (http://127.0.0.1:5000). There is no login page; the dashboard opens directly.
2. Open the simulator at http://127.0.0.1:5000/dev/simulator in a second tab. It is not in the sidebar; type the address.
3. Send vehicles with the demo data:

| Card | Plate | Expected |
|---|---|---|
| Maria Santos `04A1B2C3` | `ABC1234` | Opens automatically (NEU) |
| Maria Santos | `ZZZ0000` | Opens automatically: the card is enough, plate is only recorded |
| Maria Santos | *unreadable* | Opens, plate filled from the card, flagged "Plate unreadable" |
| Juan Dela Cruz `04D4E5F6` | `NEU5678` | Waits for guard (card expired) |
| Ana Reyes `0477889A` | `XYZ9012` | Waits for guard (card blocked) |
| No card | `VIS4321` | Waits for guard (returning visitor) |
| No card | any new plate | Waits for guard (first visit) |

When a vehicle has to wait, a pop-up with a beep appears on every dashboard page. Click **Review** to open it on Live Log, then **Open barrier** or **Deny**. Browsers only play sound after you have clicked somewhere on the page once. Use the IR switch in the simulator to drive a vehicle through; the barrier closes 3 s after the IR sensor is clear.

**Alerts** lists finished records to check later: plate unreadable, exit without entry, expired or blocked card, and vehicles the guard denied. Click **Mark as reviewed** to move one to the Reviewed tab. In the sidebar, the amber badge on Live Log counts vehicles waiting now; the red badge on Alerts counts alerts not yet reviewed.

After pulling new code, run `flask init-db` once. It adds any new database columns and keeps your existing records.

## Tests
```powershell
pytest
```
`tests/test_access_rules.py` has one test per row of the documentation's entrance and exit tables. `tests/test_gate_flow.py` runs the whole pipeline against a temporary database, including Socket.IO.

## Project layout
```
config.py               settings (overridable in .env)
run.py                  starts the server
scaneu/
  __init__.py           create_app()
  schema.sql            database tables
  db.py                 connection + CLI: init-db, seed-demo
  gate/access_rules.py  the access rules, pure functions
  gate/service.py       card/plate lookup -> rules -> log -> barrier -> live event
  gate/controller.py    barrier control (MockGateController for now)
  gate/events.py        Socket.IO: guard Open / Deny
  guard/ logs/ admin/ dev/   pages: Live Log + Alerts, Records, Visitors, simulator
  templates/ static/
tests/
```

## Database
**Change from the documentation:** a valid NEU card opens the barrier on its own. The camera's plate is recorded but no longer checked against the card, so the "NEU, plate mismatch" case was removed (team decision).

These are the six tables from the documentation (`users`, `vehicles`, `non_neu_vehicles`, `vehicle_logs`, `visit_details`, `guard_actions`). There is no login (team decision), so `guard_actions` records the action and time but not which guard. Two additions to the documented design:
- `vehicle_logs.access_result` also allows **Pending**, the state between arrival and the guard's decision.
- `vehicle_logs.pending_lane` (`entrance` / `exit`) marks which lane a vehicle is waiting at.

Plates are stored normalized: `ABC 1234` and `abc-1234` are both stored as `ABC1234`. Images are saved under `data/images/YYYY-MM-DD/`; the database stores only their paths.

## Arduino serial protocol (planned)
This is one text line per message over USB at 9600 baud:

| Direction | Message | Meaning |
|---|---|---|
| Arduino → Pi | `UID:04A1B2C3` | Card tapped |
| Arduino → Pi | `IR:1` / `IR:0` | Vehicle under barrier / clear |
| Arduino → Pi | `BTN` | Manual override button pressed |
| Pi → Arduino | `OPEN` | Lift barrier, green LED, short beep |
| Pi → Arduino | `DENY` | Keep closed, red LED, long beep |
| Pi → Arduino | `CLOSE` | Lower barrier (Arduino refuses while IR detects a vehicle) |

A `SerialGateController` with the same methods as `MockGateController` will replace the mock on the Pi.

## Next steps
- Guard form to register visitor details (driver, ID type, purpose, destination → `visit_details`)
- Admin add/edit for card holders and vehicles
- Serial link to the Arduinos, camera capture and plate recognition (YOLO11n + OCR)
- Cloud backup of rows with `synced = 0`
- Pi deployment: set `SCANEU_HOST=0.0.0.0`, `SCANEU_DEBUG=0` and `SCANEU_SIMULATOR=0`, then run `run.py` as a systemd service
