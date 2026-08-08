"""Merge engine: combine per-source canonical challenges into one record.

Priority order for every business field:
    manual override > Current (ActivityChallengeAssets) > Legacy > derived
Legacy raw data is always preserved in source_records; nothing is discarded.
"""

from __future__ import annotations

import logging
from typing import Any

from ..definition.models import SCOPE_UNKNOWN, CanonicalChallenge
from .conflicts import detect_conflicts

logger = logging.getLogger(__name__)

# Source priority: earlier wins.
_SOURCE_PRIORITY = ("current", "legacy")

# Field -> pick-first-non-empty strategy.
_FIRST_FIELDS = (
    "title_zh",
    "title_en",
    "year",
    "visibility_start",
    "visibility_end",
    "availability_start",
    "availability_end",
    "predicate_raw",
    "predicate_human",
    "trigger_mask",
    "badge_shape",
    "display_order",
)


def _first_non_empty(challenges: list[CanonicalChallenge], field: str, ordered: list[CanonicalChallenge]) -> Any:
    for challenge in ordered:
        value = getattr(challenge, field)
        if value is not None and value != "" and (not isinstance(value, list) or value):
            return value
    return None


def merge_challenges(challenges: list[CanonicalChallenge]) -> CanonicalChallenge:
    """Merge one or more per-source challenges sharing a canonical_id."""
    if not challenges:
        raise ValueError("merge_challenges called with no challenges")
    if len(challenges) == 1:
        return _copy_with_merged_sources(challenges[0], challenges)

    detect_conflicts(challenges)

    # Sort by source priority (stable; keeps legacy as fallback).
    ordered = sorted(
        challenges,
        key=lambda c: _SOURCE_PRIORITY.index(c.sources[0]) if c.sources and c.sources[0] in _SOURCE_PRIORITY else len(_SOURCE_PRIORITY),
    )
    base = challenges[0]

    merged = _copy_with_merged_sources(base, challenges)
    for field in _FIRST_FIELDS:
        value = _first_non_empty(challenges, field, ordered)
        if value is not None:
            setattr(merged, field, value)

    # Predicate parsed flag: true if any source parsed successfully.
    merged.predicate_parsed = any(c.predicate_parsed for c in challenges)

    # Scope: prefer non-unknown from higher priority source.
    for challenge in ordered:
        if challenge.scope_type != SCOPE_UNKNOWN:
            merged.scope_type = challenge.scope_type
            merged.country_codes = list(challenge.country_codes)
            break

    # Alert dates: union across sources.
    merged.alert_dates = sorted({d for c in challenges for d in c.alert_dates})

    # Sources list: union preserving priority order.
    merged.sources = [s for s in _SOURCE_PRIORITY if s in {s for c in challenges for s in c.sources}]

    return merged


def _copy_with_merged_sources(base: CanonicalChallenge, challenges: list[CanonicalChallenge]) -> CanonicalChallenge:
    """Return a shallow copy of ``base`` with unioned source_records."""
    merged_records: dict[str, dict[str, Any]] = {}
    for challenge in challenges:
        merged_records.update(challenge.source_records)
    copy = CanonicalChallenge.from_dict(base.to_dict())
    copy.source_records = merged_records
    return copy