DROP TRIGGER entries_locked_fields;
--> statement-breakpoint
CREATE TRIGGER entries_locked_fields
BEFORE UPDATE ON entries
WHEN NEW.id IS NOT OLD.id
  OR NEW.request_id IS NOT OLD.request_id
  OR NEW.victim_name IS NOT OLD.victim_name
  OR NEW.dob IS NOT OLD.dob
  OR NEW.pin IS NOT OLD.pin
  OR NEW.recorded_at IS NOT OLD.recorded_at
  OR NEW.mo IS NOT OLD.mo
  OR NEW.mobile IS NOT OLD.mobile
  OR NEW.created_by IS NOT OLD.created_by
BEGIN
    SELECT RAISE(ABORT, 'Saved personal and incident details cannot be changed');
END;
--> statement-breakpoint
DROP TRIGGER entries_remark_version;
--> statement-breakpoint
CREATE TRIGGER entries_remark_version
BEFORE UPDATE ON entries
WHEN NOT (
  (
    NEW.calling_helpline IS OLD.calling_helpline
    AND NEW.notice_helpline IS OLD.notice_helpline
    AND NEW.helpline_version IS OLD.helpline_version
    AND NEW.helpline_updated_at IS OLD.helpline_updated_at
    AND NEW.helpline_updated_by IS OLD.helpline_updated_by
    AND NEW.remarks_version = OLD.remarks_version + 1
    AND NEW.remarks_updated_at IS NOT NULL
    AND NEW.remarks_updated_by IS NOT NULL
  ) OR (
    NEW.remarks IS OLD.remarks
    AND NEW.remarks_version IS OLD.remarks_version
    AND NEW.remarks_updated_at IS OLD.remarks_updated_at
    AND NEW.remarks_updated_by IS OLD.remarks_updated_by
    AND NEW.helpline_version = OLD.helpline_version + 1
    AND NEW.helpline_updated_at IS NOT NULL
    AND NEW.helpline_updated_by IS NOT NULL
  )
)
BEGIN
    SELECT RAISE(ABORT, 'Use a versioned remarks update or admin helpline assignment with audit details');
END;
--> statement-breakpoint
DROP TRIGGER entries_audit_remark;
--> statement-breakpoint
CREATE TRIGGER entries_audit_remark
AFTER UPDATE ON entries
WHEN NEW.remarks_version != OLD.remarks_version
BEGIN
    INSERT INTO remark_history
        (entry_id, old_remarks, new_remarks, changed_at, changed_by, version)
    VALUES (NEW.id, OLD.remarks, NEW.remarks, NEW.remarks_updated_at,
            NEW.remarks_updated_by, NEW.remarks_version);
END;
--> statement-breakpoint
CREATE TRIGGER entries_audit_helpline
AFTER UPDATE ON entries
WHEN NEW.helpline_version != OLD.helpline_version
BEGIN
    INSERT INTO helpline_history
        (entry_id, old_calling_helpline, new_calling_helpline,
         old_notice_helpline, new_notice_helpline, changed_at, changed_by, version)
    VALUES (NEW.id, OLD.calling_helpline, NEW.calling_helpline,
            OLD.notice_helpline, NEW.notice_helpline, NEW.helpline_updated_at,
            NEW.helpline_updated_by, NEW.helpline_version);
END;
--> statement-breakpoint
CREATE TRIGGER helpline_history_no_update
BEFORE UPDATE ON helpline_history BEGIN
    SELECT RAISE(ABORT, 'Helpline history cannot be changed');
END;
--> statement-breakpoint
CREATE TRIGGER helpline_history_no_delete
BEFORE DELETE ON helpline_history BEGIN
    SELECT RAISE(ABORT, 'Helpline history cannot be deleted');
END;
