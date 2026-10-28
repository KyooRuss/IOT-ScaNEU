"""The gate pipeline against a real (temporary) database, as the simulator drives it."""
from scaneu.db import TABLES, get_db
from scaneu.extensions import socketio
from scaneu.gate import service


def log(app, log_id):
    with app.app_context():
        return dict(get_db().execute("SELECT * FROM vehicle_logs WHERE id = ?", (log_id,)).fetchone())


def test_schema_has_all_tables(app):
    with app.app_context():
        names = {r[0] for r in get_db().execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert set(TABLES) <= names
        assert get_db().execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_neu_entry_then_exit_records_stay(app):
    with app.app_context():
        log_id, d = service.handle_vehicle("entrance", "04a1b2c3", "abc 1234")
    assert d.open_barrier
    assert app.extensions["gate_controller"].snapshot()["entrance"]["barrier"] == "open"
    row = log(app, log_id)
    assert row["access_result"] == "Granted" and row["plate_read"] == "ABC1234" and row["pending_lane"] is None

    with app.app_context():
        exit_id, d = service.handle_vehicle("exit", "04A1B2C3", "ABC1234")
    assert d.open_barrier and exit_id == log_id
    row = log(app, log_id)
    assert row["time_out"] is not None and row["stay_duration_s"] is not None


def test_expired_card_then_guard_opens(app):
    with app.app_context():
        log_id, d = service.handle_vehicle("entrance", "04D4E5F6", "NEU5678")
    assert not d.open_barrier
    assert log(app, log_id)["pending_lane"] == "entrance"

    with app.app_context():
        service.resolve_pending(log_id, "open")
        actions = get_db().execute("SELECT action FROM guard_actions WHERE log_id = ?", (log_id,)).fetchall()
    row = log(app, log_id)
    assert row["access_result"] == "Granted by guard" and row["pending_lane"] is None
    assert [a["action"] for a in actions] == ["open"]


def test_first_time_visitor_is_registered_when_guard_opens(app):
    with app.app_context():
        log_id, _ = service.handle_vehicle("entrance", None, "NEW 7777")
        service.resolve_pending(log_id, "open")
        visitor = get_db().execute("SELECT * FROM non_neu_vehicles WHERE plate_number = 'NEW7777'").fetchone()
    assert visitor is not None and visitor["visit_count"] == 1
    assert log(app, log_id)["non_neu_vehicle_id"] == visitor["id"]


def test_visitor_exit_waits_for_guard_then_closes_record(app):
    with app.app_context():
        log_id, _ = service.handle_vehicle("entrance", None, "VIS4321")
        service.resolve_pending(log_id, "open")
        exit_id, d = service.handle_vehicle("exit", None, "VIS4321")
    assert exit_id == log_id and not d.open_barrier
    assert log(app, log_id)["pending_lane"] == "exit"
    with app.app_context():
        service.resolve_pending(log_id, "open")
    row = log(app, log_id)
    assert row["time_out"] is not None and row["access_result"] == "Granted by guard"


def test_exit_without_entry_is_flagged(app):
    with app.app_context():
        log_id, d = service.handle_vehicle("exit", None, "GHOST01")
    row = log(app, log_id)
    assert not d.open_barrier and "exit_only" in row["flags"] and row["time_in"] is None


def test_denied_entry(app):
    with app.app_context():
        log_id, _ = service.handle_vehicle("entrance", None, "BAD0001")
        service.resolve_pending(log_id, "deny")
    assert log(app, log_id)["access_result"] == "Denied"


def test_pages_render_without_login(client):
    assert client.get("/").headers["Location"].endswith("/guard")
    for url in ("/guard", "/alerts", "/logs", "/admin/visitors", "/dev/simulator"):
        assert client.get(url).status_code == 200, url


def test_guard_decision_over_socket(app, client):
    ws = socketio.test_client(app, flask_test_client=client)
    assert ws.is_connected()
    with app.app_context():
        log_id, _ = service.handle_vehicle("entrance", None, "SOC1234")
    ws.get_received()
    ack = ws.emit("guard_decision", {"log_id": log_id, "action": "open"}, callback=True)
    assert ack == {"ok": True}
    events = [e for e in ws.get_received() if e["name"] == "gate_event"]
    assert events and events[-1]["args"][0]["log"]["access_result"] == "Granted by guard"
    assert ws.emit("guard_decision", {"log_id": log_id, "action": "open"}, callback=True)["ok"] is False


def test_simulator_endpoint(client):
    res = client.post("/dev/simulator/vehicle", json={"lane": "entrance", "rfid_uid": "04A1B2C3", "plate": "ABC1234"})
    assert res.status_code == 200 and res.json["decision"]["open_barrier"] is True


# ---- Alerts (records to review later) ----

def alert_reasons(app, log_id):
    with app.app_context():
        row = get_db().execute(service.LOG_SELECT + " WHERE l.id = ?", (log_id,)).fetchone()
        return service.log_payload(row)["alert_reasons"]


def test_alert_reasons(app):
    with app.app_context():
        unreadable, _ = service.handle_vehicle("entrance", "04A1B2C3", None)
        exit_only, _ = service.handle_vehicle("exit", None, "GHOST01")
        expired, _ = service.handle_vehicle("entrance", "04D4E5F6", "NEU5678")
        service.resolve_pending(expired, "deny")
        normal, _ = service.handle_vehicle("entrance", "04A1B2C3", "ABC1234")
    assert alert_reasons(app, unreadable) == ["plate_unreadable"]
    assert alert_reasons(app, expired) == ["card_expired", "denied"]
    assert alert_reasons(app, normal) == []
    # Still waiting at the exit: the guard decides on Live Log first, so not an alert yet.
    assert alert_reasons(app, exit_only) == []
    with app.app_context():
        service.resolve_pending(exit_only, "open")
        assert {a["id"] for a in service.alert_logs()} == {unreadable, exit_only, expired}
    assert alert_reasons(app, exit_only) == ["exit_only"]


def test_mark_alert_reviewed(app, client):
    with app.app_context():
        log_id, _ = service.handle_vehicle("entrance", None, "BAD0001")
        service.resolve_pending(log_id, "deny")
        assert service.alert_count() == 1
    res = client.post(f"/alerts/{log_id}/review")
    assert res.status_code == 200 and res.json["log"]["reviewed_at"]
    with app.app_context():
        assert service.alert_count() == 0
        assert [a["id"] for a in service.alert_logs(reviewed=True)] == [log_id]
    assert client.post("/alerts/999/review").status_code == 404

    with app.app_context():
        for plate in ("BAD0002", "BAD0003"):
            other, _ = service.handle_vehicle("entrance", None, plate)
            service.resolve_pending(other, "deny")
        assert service.alert_count() == 2
    assert client.post("/alerts/review-all").json == {"reviewed": 2}
    with app.app_context():
        assert service.alert_count() == 0
    assert client.get("/alerts?show=reviewed").status_code == 200


def test_init_schema_adds_new_columns_and_keeps_data(tmp_path):
    from scaneu.db import SCHEMA, connect, init_schema

    # A database created before reviewed_at existed: today's schema minus that column.
    lines = SCHEMA.read_text(encoding="utf-8").splitlines()
    old_schema = "\n".join(line for line in lines if "reviewed_at" not in line)
    conn = connect(str(tmp_path / "old.db"))
    conn.executescript(old_schema)
    conn.execute("INSERT INTO vehicle_logs (plate_read, owner_type, access_result) VALUES ('OLD0001', 'NEU', 'Granted')")
    conn.commit()
    init_schema(conn)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(vehicle_logs)")}
    assert "reviewed_at" in columns
    assert conn.execute("SELECT plate_read FROM vehicle_logs").fetchone()[0] == "OLD0001"
    conn.close()
