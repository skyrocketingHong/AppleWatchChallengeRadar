"""SQLite access layer with transaction support and schema initialization."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .schema import INDEXES_SQL, SCHEMA_SQL


def utc_now() -> str:
    """Current UTC time as ISO-8601 with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DatabaseError(Exception):
    """Raised for database-level failures."""


class Database:
    """Thin wrapper around a SQLite connection.

    All writes happen inside explicit transactions; a failed transaction
    rolls back and never leaves a half-written challenge.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    # ---- lifecycle ----

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(SCHEMA_SQL)
            for index_sql in INDEXES_SQL:
                self._conn.execute(index_sql)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Explicit transaction; rolls back on any exception."""
        try:
            self._conn.execute("BEGIN")
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ---- generic helpers ----

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: list[tuple]) -> sqlite3.Cursor:
        return self._conn.executemany(sql, seq_of_params)

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    # ---- system_state ----

    def get_state(self, key: str) -> str | None:
        row = self.query_one("SELECT value FROM system_state WHERE key = ?", (key,))
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO system_state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def set_state_many(self, items: dict[str, str]) -> None:
        with self._conn:
            for key, value in items.items():
                self.execute(
                    "INSERT INTO system_state(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    # ---- notifications dedup ----

    def notification_exists(self, event_key: str) -> bool:
        row = self.query_one("SELECT 1 FROM notifications WHERE event_key = ?", (event_key,))
        return row is not None

    def record_notification(self, event_key: str, canonical_id: str, event_type: str) -> None:
        self.execute(
            "INSERT OR IGNORE INTO notifications(event_key, canonical_id, event_type, sent_at) "
            "VALUES(?, ?, ?, ?)",
            (event_key, canonical_id, event_type, utc_now()),
        )
        self._conn.commit()

    # ---- challenge queries ----

    def fetch_challenge(self, canonical_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM challenges WHERE canonical_id = ?", (canonical_id,))

    def fetch_all_challenges(self, active_only: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM challenges"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY availability_start IS NULL, availability_start, canonical_id"
        return self.query(sql)

    def fetch_upcoming_challenges(self) -> list[sqlite3.Row]:
        today = datetime.now(timezone.utc).date().isoformat()
        return self.query(
            "SELECT * FROM challenges WHERE active = 1 AND availability_end >= ? "
            "ORDER BY availability_start IS NULL, availability_start, canonical_id",
            (today,),
        )

    def fetch_history_challenges(self) -> list[sqlite3.Row]:
        today = datetime.now(timezone.utc).date().isoformat()
        return self.query(
            "SELECT * FROM challenges WHERE active = 1 AND availability_end < ? "
            "ORDER BY availability_end DESC",
            (today,),
        )

    def fetch_source_assets(self, source: str | None = None) -> list[sqlite3.Row]:
        if source:
            return self.query(
                "SELECT * FROM source_assets WHERE source = ? ORDER BY id", (source,)
            )
        return self.query("SELECT * FROM source_assets ORDER BY id")

    def fetch_source_asset(
        self, source: str, source_identifier: str, content_type: str
    ) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM source_assets WHERE source = ? AND source_identifier = ? AND content_type = ?",
            (source, source_identifier, content_type),
        )

    def upsert_source_asset(self, conn: sqlite3.Connection, asset: dict[str, Any]) -> None:
        conn.execute(
            """INSERT INTO source_assets(
                source, asset_type, source_identifier, canonical_id,
                content_type, content_version, compatibility_version,
                sha1, relative_path, download_url, raw_metadata,
                first_seen, last_seen, active_in_catalog
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_identifier, content_type) DO UPDATE SET
                asset_type = excluded.asset_type,
                canonical_id = excluded.canonical_id,
                content_version = excluded.content_version,
                compatibility_version = excluded.compatibility_version,
                sha1 = excluded.sha1,
                relative_path = excluded.relative_path,
                download_url = excluded.download_url,
                raw_metadata = excluded.raw_metadata,
                last_seen = excluded.last_seen,
                active_in_catalog = excluded.active_in_catalog
            """,
            (
                asset["source"],
                asset["asset_type"],
                asset["source_identifier"],
                asset.get("canonical_id"),
                asset.get("content_type"),
                asset.get("content_version"),
                asset.get("compatibility_version"),
                asset.get("sha1"),
                asset.get("relative_path"),
                asset.get("download_url"),
                asset.get("raw_metadata"),
                asset["first_seen"],
                asset["last_seen"],
                1 if asset.get("active_in_catalog", True) else 0,
            ),
        )

    def mark_assets_removed(self, conn: sqlite3.Connection, source: str, seen_keys: set[str]) -> None:
        """Mark assets of a source absent from a successful catalog as inactive."""
        rows = conn.execute(
            "SELECT source, source_identifier, content_type, active_in_catalog "
            "FROM source_assets WHERE source = ? AND active_in_catalog = 1",
            (source,),
        ).fetchall()
        for row in rows:
            key = (row["source_identifier"], row["content_type"])
            if key not in seen_keys:
                conn.execute(
                    "UPDATE source_assets SET active_in_catalog = 0, last_seen = ? "
                    "WHERE source = ? AND source_identifier = ? AND content_type = ?",
                    (utc_now(), source, row["source_identifier"], row["content_type"]),
                )

    def mark_assets_seen(self, conn: sqlite3.Connection, source: str, seen_keys: set[str]) -> None:
        """Mark assets present in a successful catalog as active (re-activate)."""
        for source_identifier, content_type in seen_keys:
            conn.execute(
                "UPDATE source_assets SET active_in_catalog = 1 "
                "WHERE source = ? AND source_identifier = ? AND content_type = ?",
                (source, source_identifier, content_type),
            )

    def upsert_challenge(self, conn: sqlite3.Connection, challenge: dict[str, Any]) -> None:
        conn.execute(
            """INSERT INTO challenges(
                canonical_id, title_zh, title_en, year,
                visibility_start, visibility_end,
                availability_start, availability_end,
                alert_dates,
                scope_type, country_codes,
                predicate_raw, predicate_human, predicate_parsed,
                trigger_mask, badge_shape, display_order,
                sources,
                first_seen, last_seen, updated_at, sequence, active
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_id) DO UPDATE SET
                title_zh = excluded.title_zh,
                title_en = excluded.title_en,
                year = excluded.year,
                visibility_start = excluded.visibility_start,
                visibility_end = excluded.visibility_end,
                availability_start = excluded.availability_start,
                availability_end = excluded.availability_end,
                alert_dates = excluded.alert_dates,
                scope_type = excluded.scope_type,
                country_codes = excluded.country_codes,
                predicate_raw = excluded.predicate_raw,
                predicate_human = excluded.predicate_human,
                predicate_parsed = excluded.predicate_parsed,
                trigger_mask = excluded.trigger_mask,
                badge_shape = excluded.badge_shape,
                display_order = excluded.display_order,
                sources = excluded.sources,
                last_seen = excluded.last_seen,
                updated_at = excluded.updated_at,
                sequence = excluded.sequence,
                active = excluded.active
            """,
            (
                challenge["canonical_id"],
                challenge.get("title_zh"),
                challenge.get("title_en"),
                challenge.get("year"),
                challenge.get("visibility_start"),
                challenge.get("visibility_end"),
                challenge.get("availability_start"),
                challenge.get("availability_end"),
                challenge.get("alert_dates"),
                challenge.get("scope_type", "unknown"),
                challenge.get("country_codes"),
                challenge.get("predicate_raw"),
                challenge.get("predicate_human"),
                1 if challenge.get("predicate_parsed") else 0,
                challenge.get("trigger_mask"),
                challenge.get("badge_shape"),
                challenge.get("display_order"),
                challenge.get("sources"),
                challenge["first_seen"],
                challenge["last_seen"],
                challenge["updated_at"],
                challenge.get("sequence", 0),
                1 if challenge.get("active", True) else 0,
            ),
        )

    def deactivate_challenge(self, conn: sqlite3.Connection, canonical_id: str) -> None:
        conn.execute(
            "UPDATE challenges SET active = 0, updated_at = ? WHERE canonical_id = ?",
            (utc_now(), canonical_id),
        )

    def all_canonical_ids(self) -> set[str]:
        rows = self.query("SELECT canonical_id FROM challenges WHERE active = 1")
        return {row["canonical_id"] for row in rows}

    def challenge_business_fingerprint(self, canonical_id: str) -> str | None:
        """Fingerprint of business fields used for UPDATED detection."""
        row = self.fetch_challenge(canonical_id)
        if row is None:
            return None
        parts = [
            row["availability_start"],
            row["availability_end"],
            row["visibility_start"],
            row["visibility_end"],
            row["scope_type"],
            row["country_codes"],
            row["predicate_raw"],
            row["trigger_mask"] and str(row["trigger_mask"]),
        ]
        return "|".join(p or "" for p in parts)