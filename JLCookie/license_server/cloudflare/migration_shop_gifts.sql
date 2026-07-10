CREATE TABLE IF NOT EXISTS shop_gifts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  tier TEXT NOT NULL,
  plan TEXT NOT NULL,
  duration_days INTEGER NOT NULL,
  note TEXT,
  created_at INTEGER NOT NULL,
  claimed_at INTEGER,
  FOREIGN KEY (user_id) REFERENCES shop_users(id),
  FOREIGN KEY (code) REFERENCES lic_keys(code)
);
