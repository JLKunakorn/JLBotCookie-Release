CREATE TABLE IF NOT EXISTS discord_roles (
  code TEXT PRIMARY KEY,
  discord_user_id TEXT NOT NULL,
  tier TEXT NOT NULL,
  is_lifetime INTEGER NOT NULL DEFAULT 0,
  assigned_at INTEGER NOT NULL,
  last_checked_at INTEGER NOT NULL,
  FOREIGN KEY (code) REFERENCES lic_keys(code)
);

CREATE INDEX IF NOT EXISTS idx_discord_roles_user ON discord_roles(discord_user_id);
