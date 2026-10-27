PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    calling_helpline TEXT NOT NULL DEFAULT '',
    victim_name TEXT NOT NULL CHECK(length(victim_name) BETWEEN 2 AND 120),
    dob TEXT NOT NULL DEFAULT '',
    pin TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL,
    mo TEXT NOT NULL CHECK(length(mo) BETWEEN 1 AND 3000),
    mobile TEXT NOT NULL,
    notice_helpline TEXT NOT NULL DEFAULT '',
    remarks TEXT NOT NULL DEFAULT '' CHECK(length(remarks) <= 5000),
    created_by TEXT NOT NULL,
    remarks_version INTEGER NOT NULL DEFAULT 0,
    remarks_updated_at TEXT,
    remarks_updated_by TEXT
);

CREATE TABLE IF NOT EXISTS remark_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES entries(id),
    old_remarks TEXT NOT NULL,
    new_remarks TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    version INTEGER NOT NULL,
    UNIQUE(entry_id, version)
);

CREATE TRIGGER IF NOT EXISTS entries_no_delete
BEFORE DELETE ON entries BEGIN
    SELECT RAISE(ABORT, 'Saved entries cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS entries_locked_fields
BEFORE UPDATE ON entries
WHEN NEW.id IS NOT OLD.id
  OR NEW.request_id IS NOT OLD.request_id
  OR NEW.calling_helpline IS NOT OLD.calling_helpline
  OR NEW.victim_name IS NOT OLD.victim_name
  OR NEW.dob IS NOT OLD.dob
  OR NEW.pin IS NOT OLD.pin
  OR NEW.recorded_at IS NOT OLD.recorded_at
  OR NEW.mo IS NOT OLD.mo
  OR NEW.mobile IS NOT OLD.mobile
  OR NEW.notice_helpline IS NOT OLD.notice_helpline
  OR NEW.created_by IS NOT OLD.created_by
BEGIN
    SELECT RAISE(ABORT, 'Only remarks can be changed');
END;

CREATE TRIGGER IF NOT EXISTS entries_remark_version
BEFORE UPDATE ON entries
WHEN NEW.remarks_version != OLD.remarks_version + 1
  OR NEW.remarks_updated_at IS NULL
  OR NEW.remarks_updated_by IS NULL
BEGIN
    SELECT RAISE(ABORT, 'A remark update requires version and audit details');
END;

CREATE TRIGGER IF NOT EXISTS entries_audit_remark
AFTER UPDATE ON entries BEGIN
    INSERT INTO remark_history
        (entry_id, old_remarks, new_remarks, changed_at, changed_by, version)
    VALUES (NEW.id, OLD.remarks, NEW.remarks, NEW.remarks_updated_at,
            NEW.remarks_updated_by, NEW.remarks_version);
END;

CREATE TRIGGER IF NOT EXISTS history_no_update
BEFORE UPDATE ON remark_history BEGIN
    SELECT RAISE(ABORT, 'Remark history cannot be changed');
END;

CREATE TRIGGER IF NOT EXISTS history_no_delete
BEFORE DELETE ON remark_history BEGIN
    SELECT RAISE(ABORT, 'Remark history cannot be deleted');
END;

CREATE INDEX IF NOT EXISTS entries_date_idx ON entries(recorded_at);
