"""SQLite schema definition for challenge-radar."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS challenges (
    canonical_id TEXT PRIMARY KEY,

    title_zh TEXT,
    title_en TEXT,

    year INTEGER,

    visibility_start TEXT,
    visibility_end TEXT,

    availability_start TEXT,
    availability_end TEXT,

    alert_dates TEXT,

    scope_type TEXT NOT NULL DEFAULT 'unknown',
    country_codes TEXT,

    predicate_raw TEXT,
    predicate_human TEXT,
    predicate_parsed INTEGER NOT NULL DEFAULT 0,

    trigger_mask INTEGER,

    badge_shape TEXT,
    display_order INTEGER,

    sources TEXT,

    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    sequence INTEGER NOT NULL DEFAULT 0,

    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS source_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source TEXT NOT NULL,
    asset_type TEXT NOT NULL,

    source_identifier TEXT,
    canonical_id TEXT,

    content_type TEXT,
    content_version TEXT,
    compatibility_version INTEGER,

    sha1 TEXT,
    relative_path TEXT,
    download_url TEXT,

    raw_metadata TEXT,

    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,

    active_in_catalog INTEGER NOT NULL DEFAULT 1,

    UNIQUE(source, source_identifier, content_type)
);

CREATE TABLE IF NOT EXISTS challenge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    canonical_id TEXT NOT NULL,
    source TEXT NOT NULL,

    fingerprint TEXT NOT NULL,

    normalized_json TEXT NOT NULL,

    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    event_key TEXT UNIQUE NOT NULL,

    canonical_id TEXT NOT NULL,

    event_type TEXT NOT NULL,

    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_source_assets_canonical ON source_assets(canonical_id);",
    "CREATE INDEX IF NOT EXISTS idx_history_canonical ON challenge_history(canonical_id);",
    "CREATE INDEX IF NOT EXISTS idx_notifications_canonical ON notifications(canonical_id);",
]