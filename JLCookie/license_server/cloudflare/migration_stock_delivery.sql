-- Run only if you already deployed the older schema before stock-delivery mode.
ALTER TABLE lic_keys ADD COLUMN status TEXT NOT NULL DEFAULT 'stock';
ALTER TABLE lic_keys ADD COLUMN delivered_at INTEGER;
ALTER TABLE lic_keys ADD COLUMN order_id TEXT;
ALTER TABLE lic_keys ADD COLUMN customer_ref TEXT;

UPDATE lic_keys SET status = 'delivered' WHERE expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_lic_keys_stock ON lic_keys(status, plan, duration_days, max_seats, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lic_keys_order_id ON lic_keys(order_id) WHERE order_id IS NOT NULL;
