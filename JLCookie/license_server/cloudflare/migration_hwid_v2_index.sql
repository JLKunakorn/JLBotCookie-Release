-- The production D1 database already has the nullable hwid_v2 column.
-- Fresh databases receive it from schema.sql; this migration adds the lookup index safely.
CREATE INDEX IF NOT EXISTS idx_lic_seats_code_hwid_v2 ON lic_seats(code, hwid_v2);
