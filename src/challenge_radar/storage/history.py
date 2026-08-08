"""Challenge history recording.

Every real change of a Challenge Definition is preserved in challenge_history.
The fingerprint is derived from the normalized business data, so a pure asset
hash change (new ZIP URL / SHA-1) with identical business data also leaves a
record, but does not bump the canonical sequence.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .database import utc_now


def fingerprint_dict(data: dict[str, Any]) -> str:
    """Deterministic fingerprint over a normalized challenge dict."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def record_history(
    conn: sqlite3.Connection,
    canonical_id: str,
    source: str,
    normalized: dict[str, Any],
    fingerprint: str | None = None,
) -> str:
    """Insert one history row; returns the recorded fingerprint."""
    fp = fingerprint or fingerprint_dict(normalized)
    conn.execute(
        "INSERT INTO challenge_history(canonical_id, source, fingerprint, normalized_json, detected_at) "
        "VALUES(?, ?, ?, ?, ?)",
        (canonical_id, source, fp, json.dumps(normalized, ensure_ascii=False, sort_keys=True), utc_now()),
    )
    return fp


def latest_fingerprint(conn: sqlite3.Connection, canonical_id: str, source: str) -> str | None:
    row = conn.execute(
        "SELECT fingerprint FROM challenge_history "
        "WHERE canonical_id = ? AND source = ? "
        "ORDER BY id DESC LIMIT 1",
        (canonical_id, source),
    ).fetchone()
    return row["fingerprint"] if row else None