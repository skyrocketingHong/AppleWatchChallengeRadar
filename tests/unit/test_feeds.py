"""Feed filtering tests for all six ICS calendars."""

from __future__ import annotations

from challenge_radar.calendar.feeds import filter_feed
from challenge_radar.definition.models import SCOPE_GLOBAL, SCOPE_REGIONAL, SCOPE_UNKNOWN, CanonicalChallenge

from ..conftest import make_config


def _c(
    canonical_id: str,
    scope_type: str = SCOPE_GLOBAL,
    country_codes: list[str] | None = None,
    availability_start: str | None = "2030-01-01",
    availability_end: str | None = "2030-01-01",
) -> CanonicalChallenge:
    return CanonicalChallenge(
        canonical_id=canonical_id,
        scope_type=scope_type,
        country_codes=country_codes or [],
        availability_start=availability_start,
        availability_end=availability_end,
    )


def _challenges():
    return [
        _c("GLOBAL_FUTURE"),
        _c("CN_ONLY", SCOPE_REGIONAL, ["CN"], "2030-02-01", "2030-02-01"),
        _c("US_ONLY", SCOPE_REGIONAL, ["US"], "2030-03-01", "2030-03-01"),
        _c("UNKNOWN_SCOPE", SCOPE_UNKNOWN),
        _c("HISTORY", availability_start="2000-01-01", availability_end="2000-01-02"),
    ]


def test_all_contains_everything():
    config = make_config()
    assert len(filter_feed("all", _challenges(), config)) == 5


def test_history_only_past():
    config = make_config()
    ids = {c.canonical_id for c in filter_feed("history", _challenges(), config)}
    assert ids == {"HISTORY"}


def test_upcoming_excludes_history():
    config = make_config()
    ids = {c.canonical_id for c in filter_feed("upcoming", _challenges(), config)}
    assert "HISTORY" not in ids
    assert "GLOBAL_FUTURE" in ids


def test_global_excludes_regional_and_unknown():
    config = make_config()
    ids = {c.canonical_id for c in filter_feed("global", _challenges(), config)}
    # Document 58: global.ics = scope_type == global (history included).
    assert "GLOBAL_FUTURE" in ids
    assert "HISTORY" in ids
    assert "CN_ONLY" not in ids
    assert "US_ONLY" not in ids
    assert "UNKNOWN_SCOPE" not in ids


def test_cn_includes_global_and_cn_only():
    config = make_config()
    ids = {c.canonical_id for c in filter_feed("cn", _challenges(), config)}
    assert "GLOBAL_FUTURE" in ids
    assert "CN_ONLY" in ids
    assert "US_ONLY" not in ids
    assert "UNKNOWN_SCOPE" not in ids


def test_us_includes_global_and_us_only():
    config = make_config()
    ids = {c.canonical_id for c in filter_feed("us", _challenges(), config)}
    assert "GLOBAL_FUTURE" in ids
    assert "US_ONLY" in ids
    assert "CN_ONLY" not in ids


def test_cn_without_global():
    config = make_config({"feeds": {"cn": {"enabled": True, "includeGlobal": False, "regions": ["CN"]}}})
    ids = {c.canonical_id for c in filter_feed("cn", _challenges(), config)}
    assert "GLOBAL_FUTURE" not in ids
    assert "CN_ONLY" in ids