"""Source-level diff between previously seen assets and the latest catalog.

Two-level diff design:
- Source diff classifies each asset of a source as NEW / UPDATED / UNCHANGED /
  REMOVED, plus FETCH_FAILED / PARSE_FAILED at the source level.
- Canonical diff (NEW_CHALLENGE / UPDATED_CHALLENGE / UNCHANGED) is computed
  later from merged business data and drives ICS + notifications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

NEW = "NEW"
UPDATED = "UPDATED"
UNCHANGED = "UNCHANGED"
REMOVED = "REMOVED"
FETCH_FAILED = "FETCH_FAILED"
PARSE_FAILED = "PARSE_FAILED"


@dataclass
class SourceDiffResult:
    source: str
    status: str  # FETCH_FAILED | PARSE_FAILED | OK
    error: str | None = None
    changes: dict[str, str] = field(default_factory=dict)  # asset key -> status
    removed_keys: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return self.status == "OK"

    def new_keys(self) -> list[str]:
        return [k for k, v in self.changes.items() if v == NEW]

    def updated_keys(self) -> list[str]:
        return [k for k, v in self.changes.items() if v == UPDATED]


def diff_assets(
    source: str,
    previous: dict[str, str],
    current: dict[str, str],
) -> SourceDiffResult:
    """Compare {asset_key: fingerprint} maps and classify changes.

    A REMOVED asset is only reported when the caller has a successful catalog;
    the caller decides whether to act on it (never on fetch failure).
    """
    result = SourceDiffResult(source=source, status="OK")
    for key, fp in current.items():
        if key not in previous:
            result.changes[key] = NEW
        elif previous[key] != fp:
            result.changes[key] = UPDATED
        else:
            result.changes[key] = UNCHANGED
    result.removed_keys = set(previous.keys()) - set(current.keys())
    return result