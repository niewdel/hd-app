-- Backfill null created_by to 'estimates@hdgrading.com' before ownership
-- checks land. This is a string-only value, not a real user row.
--
-- NOTE: clients.created_by column does not exist in this schema (verified
-- 2026-04-20). Skipped in this migration. Ownership checks for clients will
-- only allow admin/dev to delete until that column is added.

UPDATE proposals     SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
UPDATE change_orders SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
UPDATE hd_tasks      SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
UPDATE hd_reminders  SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
