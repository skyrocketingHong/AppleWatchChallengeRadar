"""Merge engine tests: field priority, conflict detection, source records."""

from __future__ import annotations

import pytest

from challenge_radar.definition.models import SCOPE_GLOBAL, CanonicalChallenge
from challenge_radar.merge.conflicts import detect_conflicts
from challenge_radar.merge.merger import merge_challenges


def _challenge(
    canonical_id: str,
    source: str,
    availability_start: str | None = "2026-08-08",
    scope_type: str = SCOPE_GLOBAL,
    country_codes: list[str] | None = None,
    predicate_human: str | None = None,
    trigger_mask: int | None = None,
) -> CanonicalChallenge:
    return CanonicalChallenge(
        canonical_id=canonical_id,
        title_zh=f"标题-{source}",
        title_en=f"Title-{source}",
        availability_start=availability_start,
        scope_type=scope_type,
        country_codes=country_codes or [],
        predicate_human=predicate_human,
        trigger_mask=trigger_mask,
        sources=[source],
        source_records={source: {"source_identifier": f"{canonical_id}-{source}"}},
    )


def test_current_wins_over_legacy():
    legacy = _challenge("EARTH_DAY_2026", "legacy", availability_start="2026-04-21", predicate_human="旧条件")
    current = _challenge("EARTH_DAY_2026", "current", availability_start="2026-04-22", predicate_human="新条件")
    merged = merge_challenges([legacy, current])
    assert merged.availability_start == "2026-04-22"
    assert merged.predicate_human == "新条件"
    assert merged.sources == ["current", "legacy"]
    assert set(merged.source_records.keys()) == {"current", "legacy"}


def test_scope_priority_current():
    legacy = _challenge("X", "legacy", scope_type="regional", country_codes=["CN"])
    current = _challenge("X", "current", scope_type=SCOPE_GLOBAL)
    merged = merge_challenges([legacy, current])
    assert merged.scope_type == SCOPE_GLOBAL
    assert merged.country_codes == []


def test_single_source_passthrough():
    only = _challenge("NEW_YEAR_2026", "current")
    merged = merge_challenges([only])
    assert merged.canonical_id == "NEW_YEAR_2026"
    assert merged.sources == ["current"]


def test_conflict_detection_reports_difference():
    legacy = _challenge("X", "legacy", availability_start="2026-08-07")
    current = _challenge("X", "current", availability_start="2026-08-08")
    warnings = detect_conflicts([legacy, current])
    assert any(w.field == "availability_start" for w in warnings)
    assert warnings[0].legacy_value == "2026-08-07"
    assert warnings[0].current_value == "2026-08-08"


def test_no_conflict_when_identical():
    legacy = _challenge("X", "legacy", availability_start="2026-08-08")
    current = _challenge("X", "current", availability_start="2026-08-08")
    assert detect_conflicts([legacy, current]) == []


def test_alert_dates_union():
    legacy = _challenge("X", "legacy")
    legacy.alert_dates = ["2026-08-06"]
    current = _challenge("X", "current")
    current.alert_dates = ["2026-08-07"]
    merged = merge_challenges([legacy, current])
    assert merged.alert_dates == ["2026-08-06", "2026-08-07"]


def test_predicate_parsed_any():
    legacy = _challenge("X", "legacy", predicate_human=None)
    legacy.predicate_parsed = False
    current = _challenge("X", "current", predicate_human="完成至少20分钟任意锻炼")
    current.predicate_parsed = True
    merged = merge_challenges([legacy, current])
    assert merged.predicate_parsed is True