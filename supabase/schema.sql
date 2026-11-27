-- ScaNEU online backup (Supabase / PostgreSQL).
--
-- A copy of the six tables on the Raspberry Pi (scaneu/schema.sql), so the Pi can
-- upload its rows exactly as they are. Run it in the Supabase SQL Editor; it is safe
-- to run again. When scaneu/schema.sql changes, change this file the same way.
--
-- * Ids come from the Pi, so they are plain BIGINT, not identity columns. The Pi sends
--   each row with its own id and sends it again when it changes (for example when the
--   car exits), so the foreign keys match on both sides.
-- * Times are Philippine local time, the same values as on the Pi.
-- * Image paths are relative to the Pi's image folder (YYYY-MM-DD/...). The photos
--   themselves are not uploaded yet.
-- * Only the Pi writes here, using the secret key, which bypasses row level security.
--   RLS is on with no policies, so the publishable key can read nothing: these tables
--   hold names, NEU IDs and card numbers.

-- Optional: remove the first draft's tables. Uncomment only if they hold nothing you need.
-- DROP TABLE IF EXISTS public.system_alerts, public.vehicle_records,
--     public.system_messages, public.vehicle_datas;

-- NEU card holders.
CREATE TABLE IF NOT EXISTS public.users (
    id          BIGINT PRIMARY KEY,
    full_name   TEXT NOT NULL,
    neu_id      TEXT NOT NULL UNIQUE,
    rfid_uid    TEXT UNIQUE,
    card_status TEXT NOT NULL DEFAULT 'Active' CHECK (card_status IN ('Active', 'Blocked')),
    valid_until DATE,                       -- NULL means no expiry
    created_at  TIMESTAMP NOT NULL
);

-- Vehicles registered to NEU card holders. One card holder can have several.
CREATE TABLE IF NOT EXISTS public.vehicles (
    id            BIGINT PRIMARY KEY,
    plate_number  TEXT NOT NULL UNIQUE,
    user_id       BIGINT NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    vehicle_type  TEXT,
    vehicle_color TEXT
);

-- Visitor vehicles, registered by the guard on the first visit.
CREATE TABLE IF NOT EXISTS public.non_neu_vehicles (
    id            BIGINT PRIMARY KEY,
    plate_number  TEXT NOT NULL UNIQUE,
    vehicle_type  TEXT,
    vehicle_color TEXT,
    driver_name   TEXT,
    id_type       TEXT,                     -- ID presented, e.g. "Driver's license"
    first_seen    TIMESTAMP NOT NULL,
    last_seen     TIMESTAMP NOT NULL,
    visit_count   INTEGER NOT NULL DEFAULT 0
);

-- One row per visit: entry fills time_in, exit fills time_out and stay_duration_s.
-- Alerts are not a separate table. A visit is an alert when its flags contain
-- plate_unreadable, exit_only, card_expired or card_blocked, or when access_result
-- is 'Denied'. reviewed_at is set when the guard marks it as reviewed.
CREATE TABLE IF NOT EXISTS public.vehicle_logs (
    id                 BIGINT PRIMARY KEY,
    plate_read         TEXT,
    owner_type         TEXT NOT NULL CHECK (owner_type IN ('NEU', 'Non-NEU', 'Unknown')),
    user_id            BIGINT REFERENCES public.users (id) ON DELETE SET NULL,
    non_neu_vehicle_id BIGINT REFERENCES public.non_neu_vehicles (id) ON DELETE SET NULL,
    rfid_uid           TEXT,
    access_result      TEXT NOT NULL
                       CHECK (access_result IN ('Pending', 'Granted', 'Granted by guard', 'Denied')),
    time_in            TIMESTAMP,
    time_out           TIMESTAMP,
    stay_duration_s    INTEGER,
    vehicle_type       TEXT,
    vehicle_color      TEXT,
    entry_image_path   TEXT,
    exit_image_path    TEXT,
    flags              TEXT NOT NULL DEFAULT '',  -- comma-separated, e.g. 'plate_unreadable,first_visit'
    pending_lane       TEXT CHECK (pending_lane IN ('entrance', 'exit')),
    reviewed_at        TIMESTAMP
);

-- Purpose and destination for visitor entries.
CREATE TABLE IF NOT EXISTS public.visit_details (
    log_id             BIGINT PRIMARY KEY REFERENCES public.vehicle_logs (id) ON DELETE CASCADE,
    purpose            TEXT,
    destination_office TEXT
);

-- Every guard decision. No guard accounts, so only the action and time.
CREATE TABLE IF NOT EXISTS public.guard_actions (
    id         BIGINT PRIMARY KEY,
    log_id     BIGINT REFERENCES public.vehicle_logs (id) ON DELETE SET NULL,
    action     TEXT NOT NULL CHECK (action IN ('open', 'deny', 'edit', 'force_capture')),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vehicles_user ON public.vehicles (user_id);
CREATE INDEX IF NOT EXISTS idx_logs_plate ON public.vehicle_logs (plate_read);
CREATE INDEX IF NOT EXISTS idx_logs_user ON public.vehicle_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_logs_non_neu ON public.vehicle_logs (non_neu_vehicle_id);
CREATE INDEX IF NOT EXISTS idx_logs_time_in ON public.vehicle_logs (time_in);
CREATE INDEX IF NOT EXISTS idx_actions_log ON public.guard_actions (log_id);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.non_neu_vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicle_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visit_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guard_actions ENABLE ROW LEVEL SECURITY;
