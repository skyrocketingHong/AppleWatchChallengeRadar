"""Normalizer tests: raw Definition payloads -> Canonical Challenge Model."""

from __future__ import annotations

from challenge_radar.definition.models import SCOPE_GLOBAL, SCOPE_REGIONAL, SCOPE_UNKNOWN
from challenge_radar.normalize.normalizer import Normalizer
from challenge_radar.sources.base import RawChallenge

from ..conftest import make_config
from ..fixtures.definitions import CHINA_FITNESS_DAY_2026, make_definition


def _normalize(definition: dict, source: str = "current") -> object:
    config = make_config()
    raw = RawChallenge(
        source=source,
        identifier=str(definition["identifier"]),
        definition=definition,
        sha1="abc123",
        content_version="2",
        compatibility_version=3,
    )
    return Normalizer(config).normalize(raw)


def test_cn_scope_and_title():
    challenge = _normalize(CHINA_FITNESS_DAY_2026)
    assert challenge.canonical_id == "CHINA_FITNESS_DAY_2026"
    assert challenge.title_zh == "全民健身日挑战"
    assert challenge.scope_type == SCOPE_REGIONAL
    assert challenge.country_codes == ["CN"]
    assert challenge.year == 2026
    assert challenge.availability_start == "2026-08-08"
    assert challenge.alert_dates == ["2026-08-07"]
    assert challenge.predicate_human == "完成至少20分钟任意锻炼"
    assert challenge.predicate_parsed is True
    assert challenge.trigger_mask == 2
    assert challenge.badge_shape == "circle"
    assert challenge.display_order == 89


def test_empty_country_codes_is_global():
    challenge = _normalize(make_definition("EARTH_DAY_2026"))
    assert challenge.scope_type == SCOPE_GLOBAL
    assert challenge.country_codes == []


def test_missing_country_codes_is_unknown():
    definition = make_definition("EARTH_DAY_2026")
    del definition["availableCountryCodes"]
    challenge = _normalize(definition)
    assert challenge.scope_type == SCOPE_UNKNOWN
    assert challenge.country_codes == []


def test_unknown_identifier_keeps_id():
    definition = make_definition("EARTH_DAY_2026", identifier="SOME_NEW_2026")
    challenge = _normalize(definition)
    assert challenge.canonical_id == "SOME_NEW_2026"
    assert challenge.title_zh is None


def test_unknown_predicate_keeps_raw_unparsed():
    definition = make_definition("EARTH_DAY_2026", predicate="mysteryField >= 5")
    challenge = _normalize(definition)
    assert challenge.predicate_raw == "mysteryField >= 5"
    assert challenge.predicate_parsed is False
    assert challenge.predicate_human is None


def test_alias_resolution():
    config = make_config({"aliases": {"LEGACY_CHINA_2026": {"canonical": "CHINA_FITNESS_DAY_2026"}}})
    raw = RawChallenge(
        source="legacy",
        identifier="LEGACY_CHINA_2026",
        definition=make_definition("CHINA_FITNESS_DAY_2026"),
    )
    challenge = Normalizer(config).normalize(raw)
    assert challenge.canonical_id == "CHINA_FITNESS_DAY_2026"


def test_new_year_uses_availability():
    challenge = _normalize(make_definition("NEW_YEAR_2026"))
    assert challenge.availability_start == "2026-01-07"
    assert challenge.availability_end == "2026-01-31"
    assert challenge.visibility_start == "2025-12-28"
    assert challenge.year == 2026