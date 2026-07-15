CREATE TABLE IF NOT EXISTS lic_keys (
  code TEXT PRIMARY KEY,
  plan TEXT NOT NULL,
  duration_days INTEGER NOT NULL,
  expires_at INTEGER,
  max_seats INTEGER NOT NULL DEFAULT 1,
  revoked INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'stock',
  delivered_at INTEGER,
  order_id TEXT,
  customer_ref TEXT,
  created_at INTEGER NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS lic_seats (
  code TEXT NOT NULL,
  hwid TEXT NOT NULL,
  hwid_v2 TEXT,
  first_seen INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  PRIMARY KEY (code, hwid)
);

CREATE INDEX IF NOT EXISTS idx_lic_seats_code ON lic_seats(code);
CREATE INDEX IF NOT EXISTS idx_lic_seats_code_hwid_v2 ON lic_seats(code, hwid_v2);
CREATE INDEX IF NOT EXISTS idx_lic_keys_stock ON lic_keys(status, plan, duration_days, max_seats, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lic_keys_order_id ON lic_keys(order_id) WHERE order_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS shop_users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  customer_ref TEXT,
  created_at INTEGER NOT NULL,
  last_login_at INTEGER
);

CREATE TABLE IF NOT EXISTS shop_sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  last_seen_at INTEGER,
  FOREIGN KEY (user_id) REFERENCES shop_users(id)
);

CREATE TABLE IF NOT EXISTS shop_orders (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  plan TEXT NOT NULL,
  plan_label TEXT NOT NULL,
  duration_days REAL NOT NULL,
  amount INTEGER NOT NULL,
  max_seats INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending_review',
  customer_ref TEXT,
  slip_name TEXT,
  slip_mime TEXT,
  slip_b64 TEXT,
  slip_uploaded_at INTEGER,
  key_code TEXT,
  created_at INTEGER NOT NULL,
  approved_at INTEGER,
  rejected_at INTEGER,
  admin_note TEXT,
  FOREIGN KEY (user_id) REFERENCES shop_users(id),
  FOREIGN KEY (key_code) REFERENCES lic_keys(code)
);

CREATE INDEX IF NOT EXISTS idx_shop_sessions_user ON shop_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_shop_sessions_exp ON shop_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_shop_orders_user ON shop_orders(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_shop_orders_status ON shop_orders(status, created_at);
CREATE INDEX IF NOT EXISTS idx_shop_orders_key ON shop_orders(key_code);
