"""Database layer tests: schema, upserts, transactions, history."""

from __future__ import annotations

import sqlite3

import pytest

from challenge_radar.storage.database import Database
from challenge_radar.storage.history import fingerprint_dict, latest_fingerprint, record_history


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.init_schema()
    yield database
    database.close()


def _row(canonical_id: str = "X_2026", **overrides) -> dict:
    base = {
        "canonical_id": canonical_id,
        "scope_type": "global",
        "country_codes": "[]",
        "alert_dates": "[]",
        "sources": '["current"]',
        "predicate_parsed": False,
        "sequence": 0,
        "active": True,
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_schema_initialized(db):
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"challenges", "source_assets", "challenge_history", "notifications", "system_state"} <= tables


def test_upsert_challenge_insert_and_update(db):
    with db.transaction() as conn:
        db.upsert_challenge(conn, _row("X_2026"))
    with db.transaction() as conn:
        db.upsert_challenge(conn, _row("X_2026", sequence=2))
    rows = db.query("SELECT * FROM challenges")
    assert len(rows) == 1
    assert rows[0]["sequence"] == 2


def test_transaction_rollback(db):
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            db.upsert_challenge(conn, _row("ROLLBACK_2026"))
            raise RuntimeError("boom")
    assert db.fetch_challenge("ROLLBACK_2026") is None


def test_source_asset_unique_and_upsert(db):
    with db.transaction() as conn:
        db.upsert_source_asset(
            conn,
            {
                "source": "current",
                "asset_type": "com.apple.MobileAsset.ActivityChallengeAssets",
                "source_identifier": "X",
                "canonical_id": "X_2026",
                "content_type": "Definition",
                "sha1": "aaa",
                "first_seen": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
                "active_in_catalog": True,
            },
        )
    with db.transaction() as conn:
        db.upsert_source_asset(
            conn,
            {
                "source": "current",
                "asset_type": "com.apple.MobileAsset.ActivityChallengeAssets",
                "source_identifier": "X",
                "canonical_id": "X_2026",
                "content_type": "Definition",
                "sha1": "bbb",
                "first_seen": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-02T00:00:00Z",
                "active_in_catalog": True,
            },
        )
    assets = db.fetch_source_assets("current")
    assert len(assets) == 1
    assert assets[0]["sha1"] == "bbb"


def test_notification_dedup(db):
    db.record_notification("NEW:X_2026", "X_2026", "NEW_CHALLENGE")
    assert db.notification_exists("NEW:X_2026")
    assert not db.notification_exists("NEW:Y_2026")


def test_history_fingerprint_change(db):
    with db.transaction() as conn:
        db.upsert_challenge(conn, _row())
        record_history(conn, "X_2026", "current", {"a": 1})
    with db.transaction() as conn:
        record_history(conn, "X_2026", "current", {"a": 2})
    rows = db.query("SELECT * FROM challenge_history")
    assert len(rows) == 2
    assert latest_fingerprint(db._conn, "X_2026", "current") is not None


def test_fingerprint_dict_deterministic():
    assert fingerprint_dict({"b": 2, "a": 1}) == fingerprint_dict({"a": 1, "b": 2})


def test_system_state_roundtrip(db):
    db.set_state("bootstrap_completed", "true")
    assert db.get_state("bootstrap_completed") == "true"


def test_mark_assets_removed(db):
    with db.transaction() as conn:
        db.upsert_source_asset(
            conn,
            {
                "source": "current",
                "asset_type": "t",
                "source_identifier": "KEEP",
                "content_type": "Definition",
                "first_seen": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
                "active_in_catalog": True,
            },
        )
        db.upsert_source_asset(
            conn,
            {
                "source": "current",
                "asset_type": "t",
                "source_identifier": "GONE",
                "content_type": "Definition",
                "first_seen": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
                "active_in_catalog": True,
            },
        )
    with db.transaction() as conn:
        db.mark_assets_removed(conn, "current", {("KEEP", "Definition")})
    rows = {r["source_identifier"]: r["active_in_catalog"] for r in db.fetch_source_assets("current")}
    assert rows == {"KEEP": 1, "GONE": 0}