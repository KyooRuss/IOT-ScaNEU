-- ScaNEU database schema (SQLite).
-- The six tables from the system documentation.
-- Times are local "YYYY-MM-DD HH:MM:SS" text. Plates are stored normalized
-- (upper-case, letters and digits only), e.g. "ABC 1234" -> "ABC1234".

-- NEU card holders. Filled by the admin.
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    neu_id      TEXT NOT NULL UNIQUE,
    rfid_uid    TEXT UNIQUE,
    card_status TEXT NOT NULL DEFAULT 'Active' CHECK (card_status IN ('Active', 'Blocked')),
    valid_until TEXT,                       -- YYYY-MM-DD; NULL means no expiry
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Vehicles registered to NEU card holders. Filled by the admin.
CREATE TABLE IF NOT EXISTS vehicles (
    id            INTEGER PRIMARY KEY,
    plate_number  TEXT NOT NULL UNIQUE,
    user_id       INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    vehicle_type  TEXT,
    vehicle_color TEXT
);

-- Visitor vehicles. Registered by the guard on the first visit, then kept up to date by the system.
CREATE TABLE IF NOT EXISTS non_neu_vehicles (
    id            INTEGER PRIMARY KEY,
    plate_number  TEXT NOT NULL UNIQUE,
    vehicle_type  TEXT,
    vehicle_color TEXT,
    driver_name   TEXT,
    id_type       TEXT,                     -- ID presented, e.g. "Driver's license"
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    visit_count   INTEGER NOT NULL DEFAULT 0
);

-- One row per visit: entry fills time_in, exit fills time_out and stay_duration_s.
CREATE TABLE IF NOT EXISTS vehicle_logs (
    id                 INTEGER PRIMARY KEY,
    plate_read         TEXT,
    owner_type         TEXT NOT NULL CHECK (owner_type IN ('NEU', 'Non-NEU', 'Unknown')),
    user_id            INTEGER REFERENCES users (id) ON DELETE SET NULL,
    non_neu_vehicle_id INTEGER REFERENCES non_neu_vehicles (id) ON DELETE SET NULL,
    rfid_uid           TEXT,
    access_result      TEXT NOT NULL
                       CHECK (access_result IN ('Pending', 'Granted', 'Granted by guard', 'Denied')),
    time_in            TEXT,
    time_out           TEXT,
    stay_duration_s    INTEGER,
    vehicle_type       TEXT,
    vehicle_color      TEXT,
    entry_image_path   TEXT,
    exit_image_path    TEXT,
    flags              TEXT NOT NULL DEFAULT '',  -- comma-separated, e.g. "plate_unreadable,first_visit"
    pending_lane       TEXT CHECK (pending_lane IN ('entrance', 'exit')),  -- set while waiting for the guard
    reviewed_at        TEXT,                    -- when the guard marked the alert as reviewed
    synced             INTEGER NOT NULL DEFAULT 0 CHECK (synced IN (0, 1))
);

-- Purpose and destination for non-NEU entries. Filled by the guard at each entry.
CREATE TABLE IF NOT EXISTS visit_details (
    log_id             INTEGER PRIMARY KEY REFERENCES vehicle_logs (id) ON DELETE CASCADE,
    purpose            TEXT,
    destination_office TEXT
);

-- Audit trail of every guard decision. Written by the system.
-- No guard account: the dashboard has no login, so only the action and time are kept.
CREATE TABLE IF NOT EXISTS guard_actions (
    id         INTEGER PRIMARY KEY,
    log_id     INTEGER REFERENCES vehicle_logs (id) ON DELETE SET NULL,
    action     TEXT NOT NULL CHECK (action IN ('open', 'deny', 'edit', 'force_capture')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_vehicles_user ON vehicles (user_id);
CREATE INDEX IF NOT EXISTS idx_logs_plate ON vehicle_logs (plate_read);
CREATE INDEX IF NOT EXISTS idx_logs_user ON vehicle_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_logs_open ON vehicle_logs (time_out, time_in);
CREATE INDEX IF NOT EXISTS idx_logs_pending ON vehicle_logs (pending_lane);
CREATE INDEX IF NOT EXISTS idx_logs_unsynced ON vehicle_logs (synced);
CREATE INDEX IF NOT EXISTS idx_actions_log ON guard_actions (log_id);
