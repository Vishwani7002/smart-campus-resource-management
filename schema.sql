-- =====================================================================
--  SMART CAMPUS RESOURCE ALLOCATION & CONFLICT MANAGEMENT SYSTEM
--  Database schema (SQLite) - normalised to 3NF
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------- 1. MASTER TABLES -----------------------------------------
CREATE TABLE departments (
    dept_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    code      TEXT NOT NULL UNIQUE
);

CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL CHECK (length(trim(full_name)) >= 2),
    email         TEXT NOT NULL UNIQUE CHECK (email LIKE '%_@_%._%'),
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student'
                  CHECK (role IN ('admin','faculty','staff','student')),
    dept_id       INTEGER REFERENCES departments(dept_id) ON DELETE SET NULL,
    phone         TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE resource_types (
    type_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    type_name    TEXT NOT NULL UNIQUE,
    icon         TEXT NOT NULL DEFAULT '▣',
    is_equipment INTEGER NOT NULL DEFAULT 0 CHECK (is_equipment IN (0,1))
);

-- ---------- 2. RESOURCES (rooms + equipment) -------------------------
CREATE TABLE resources (
    resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    type_id     INTEGER NOT NULL REFERENCES resource_types(type_id) ON DELETE RESTRICT,
    building    TEXT NOT NULL,
    floor       INTEGER NOT NULL DEFAULT 0,
    capacity    INTEGER NOT NULL DEFAULT 0 CHECK (capacity >= 0),
    status      TEXT NOT NULL DEFAULT 'available'
                CHECK (status IN ('available','maintenance','retired')),
    -- SELF-REFERENCING FK: equipment can be installed inside a room
    parent_id   INTEGER REFERENCES resources(resource_id) ON DELETE SET NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---------- 3. BOOKINGS ----------------------------------------------
CREATE TABLE bookings (
    booking_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL REFERENCES resources(resource_id) ON DELETE RESTRICT,
    user_id     INTEGER NOT NULL REFERENCES users(user_id)         ON DELETE RESTRICT,
    title       TEXT NOT NULL CHECK (length(trim(title)) > 0),
    start_time  TEXT NOT NULL,   -- 'YYYY-MM-DD HH:MM'
    end_time    TEXT NOT NULL,
    attendees   INTEGER NOT NULL DEFAULT 1 CHECK (attendees > 0),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected','cancelled','completed')),
    remarks     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (end_time > start_time),
    CHECK (start_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]'),
    CHECK (end_time   GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]')
);

-- ---------- 4. MAINTENANCE -------------------------------------------
CREATE TABLE maintenance (
    maint_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL REFERENCES resources(resource_id) ON DELETE CASCADE,
    issue       TEXT NOT NULL,
    technician  TEXT,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'scheduled'
                CHECK (status IN ('scheduled','in_progress','completed','cancelled')),
    created_by  INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (end_time > start_time)
);

-- ---------- 5. AUDIT + NOTIFICATIONS ---------------------------------
CREATE TABLE audit_log (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id  INTEGER,
    action     TEXT NOT NULL,
    details    TEXT,
    logged_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE notifications (
    notif_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message    TEXT NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---------- 6. INDEXES (fast overlap detection & lookups) ------------
CREATE INDEX idx_bookings_resource_time ON bookings(resource_id, start_time, end_time);
CREATE INDEX idx_bookings_user          ON bookings(user_id);
CREATE INDEX idx_bookings_status        ON bookings(status);
CREATE INDEX idx_maint_resource_time    ON maintenance(resource_id, start_time, end_time);
CREATE INDEX idx_resources_type         ON resources(type_id);
CREATE INDEX idx_notif_user             ON notifications(user_id, is_read);

-- ---------- 7. VIEWS --------------------------------------------------
CREATE VIEW v_booking_details AS
SELECT b.booking_id, b.resource_id, r.name AS resource_name, t.type_name, t.icon,
       r.building, b.user_id, u.full_name AS user_name, u.email AS user_email,
       u.role, d.name AS dept_name, b.title, b.start_time, b.end_time,
       b.attendees, b.status, b.remarks, b.created_at,
       ROUND((julianday(b.end_time) - julianday(b.start_time)) * 24, 2) AS hours
FROM bookings b
JOIN resources      r ON r.resource_id = b.resource_id
JOIN resource_types t ON t.type_id     = r.type_id
JOIN users          u ON u.user_id     = b.user_id
LEFT JOIN departments d ON d.dept_id   = u.dept_id;

CREATE VIEW v_resource_utilization AS
SELECT r.resource_id, r.name, t.type_name, t.icon, r.building, r.capacity, r.status,
       COUNT(b.booking_id) AS total_bookings,
       ROUND(COALESCE(SUM((julianday(b.end_time) - julianday(b.start_time)) * 24), 0), 1) AS total_hours
FROM resources r
JOIN resource_types t ON t.type_id = r.type_id
LEFT JOIN bookings b  ON b.resource_id = r.resource_id AND b.status IN ('approved','completed')
GROUP BY r.resource_id;

-- ---------- 8. TRIGGERS: CONFLICT PREVENTION (the heart of the system)
-- Two time ranges overlap  <=>  existing.start < new.end AND existing.end > new.start

CREATE TRIGGER trg_booking_before_insert
BEFORE INSERT ON bookings
BEGIN
    SELECT RAISE(ABORT, 'UNAVAILABLE: This resource is out of service (maintenance or retired).')
    WHERE (SELECT status FROM resources WHERE resource_id = NEW.resource_id) <> 'available';

    SELECT RAISE(ABORT, 'CAPACITY: Number of attendees exceeds the capacity of this resource.')
    WHERE (SELECT capacity FROM resources WHERE resource_id = NEW.resource_id) > 0
      AND NEW.attendees > (SELECT capacity FROM resources WHERE resource_id = NEW.resource_id);

    SELECT RAISE(ABORT, 'MAINTENANCE: Resource is scheduled for maintenance during this time.')
    WHERE NEW.status IN ('pending','approved')
      AND EXISTS (SELECT 1 FROM maintenance m
                  WHERE m.resource_id = NEW.resource_id
                    AND m.status IN ('scheduled','in_progress')
                    AND m.start_time < NEW.end_time AND m.end_time > NEW.start_time);

    SELECT RAISE(ABORT, 'CONFLICT: Resource is already booked during this time slot.')
    WHERE NEW.status IN ('pending','approved')
      AND EXISTS (SELECT 1 FROM bookings b
                  WHERE b.resource_id = NEW.resource_id
                    AND b.status IN ('pending','approved')
                    AND b.start_time < NEW.end_time AND b.end_time > NEW.start_time);
END;

-- Same protection when a booking is approved / re-activated / moved
CREATE TRIGGER trg_booking_before_update
BEFORE UPDATE OF status, start_time, end_time, resource_id ON bookings
WHEN NEW.status IN ('pending','approved')
BEGIN
    SELECT RAISE(ABORT, 'CONFLICT: Another active booking already occupies this slot.')
    WHERE EXISTS (SELECT 1 FROM bookings b
                  WHERE b.resource_id = NEW.resource_id
                    AND b.booking_id <> NEW.booking_id
                    AND b.status IN ('pending','approved')
                    AND b.start_time < NEW.end_time AND b.end_time > NEW.start_time);
END;

-- ---------- 9. TRIGGERS: MAINTENANCE WORKFLOW -------------------------
-- Scheduling maintenance automatically cancels bookings that clash with it
CREATE TRIGGER trg_maint_cascade_cancel
AFTER INSERT ON maintenance
WHEN NEW.status IN ('scheduled','in_progress')
BEGIN
    UPDATE bookings
       SET status = 'cancelled',
           remarks = 'Auto-cancelled: resource scheduled for maintenance (' || NEW.issue || ')'
     WHERE resource_id = NEW.resource_id
       AND status IN ('pending','approved')
       AND start_time < NEW.end_time AND end_time > NEW.start_time;

    INSERT INTO audit_log(table_name, record_id, action, details)
    VALUES ('maintenance', NEW.maint_id, 'INSERT',
            'Maintenance scheduled for resource #' || NEW.resource_id || ': ' || NEW.issue);
END;

CREATE TRIGGER trg_maint_start_insert
AFTER INSERT ON maintenance
WHEN NEW.status = 'in_progress'
BEGIN
    UPDATE resources SET status = 'maintenance'
     WHERE resource_id = NEW.resource_id AND status = 'available';
END;

CREATE TRIGGER trg_maint_start_update
AFTER UPDATE OF status ON maintenance
WHEN NEW.status = 'in_progress' AND OLD.status <> 'in_progress'
BEGIN
    UPDATE resources SET status = 'maintenance'
     WHERE resource_id = NEW.resource_id AND status = 'available';
    INSERT INTO audit_log(table_name, record_id, action, details)
    VALUES ('maintenance', NEW.maint_id, 'STATUS_CHANGE', OLD.status || ' -> in_progress');
END;

CREATE TRIGGER trg_maint_finish
AFTER UPDATE OF status ON maintenance
WHEN NEW.status IN ('completed','cancelled') AND OLD.status <> NEW.status
BEGIN
    UPDATE resources SET status = 'available'
     WHERE resource_id = NEW.resource_id AND status = 'maintenance'
       AND NOT EXISTS (SELECT 1 FROM maintenance m
                       WHERE m.resource_id = NEW.resource_id
                         AND m.status = 'in_progress' AND m.maint_id <> NEW.maint_id);
    INSERT INTO audit_log(table_name, record_id, action, details)
    VALUES ('maintenance', NEW.maint_id, 'STATUS_CHANGE', OLD.status || ' -> ' || NEW.status);
END;

-- ---------- 10. TRIGGERS: AUDIT TRAIL + NOTIFICATIONS ------------------
CREATE TRIGGER trg_audit_booking_insert
AFTER INSERT ON bookings
BEGIN
    INSERT INTO audit_log(table_name, record_id, action, details)
    VALUES ('bookings', NEW.booking_id, 'INSERT',
            'Booking "' || NEW.title || '" created (' || NEW.status || ') for resource #' ||
            NEW.resource_id || ' ' || NEW.start_time || ' to ' || substr(NEW.end_time, 12));
END;

CREATE TRIGGER trg_audit_booking_status
AFTER UPDATE OF status ON bookings
WHEN OLD.status <> NEW.status
BEGIN
    INSERT INTO audit_log(table_name, record_id, action, details)
    VALUES ('bookings', NEW.booking_id, 'STATUS_CHANGE', OLD.status || ' -> ' || NEW.status);
END;

CREATE TRIGGER trg_notify_booking
AFTER UPDATE OF status ON bookings
WHEN OLD.status <> NEW.status
 AND (NEW.status IN ('approved','rejected') OR (NEW.status = 'cancelled' AND NEW.remarks LIKE 'Auto-cancelled%'))
BEGIN
    INSERT INTO notifications(user_id, message)
    VALUES (NEW.user_id,
            'Your booking "' || NEW.title || '" on ' || NEW.start_time || ' is now ' || NEW.status ||
            COALESCE('. ' || NEW.remarks, '.'));
END;

CREATE TRIGGER trg_audit_user_insert
AFTER INSERT ON users
BEGIN
    INSERT INTO audit_log(table_name, record_id, action, details)
    VALUES ('users', NEW.user_id, 'REGISTER', NEW.full_name || ' registered as ' || NEW.role);
END;

CREATE TRIGGER trg_audit_resource_status
AFTER UPDATE OF status ON resources
WHEN OLD.status <> NEW.status
BEGIN
    INSERT INTO audit_log(table_name, record_id, action, details)
    VALUES ('resources', NEW.resource_id, 'STATUS_CHANGE',
            NEW.name || ': ' || OLD.status || ' -> ' || NEW.status);
END;
