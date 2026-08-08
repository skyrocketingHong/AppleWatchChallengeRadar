"""Calendar generation tests: events, UID stability, sequence, atomic writes."""

from __future__ import annotations

from datetime import date

import pytest
from icalendar import Calendar

from challenge_radar.calendar.event import build_event
from challenge_radar.calendar.generator import CalendarGenerator
from challenge_radar.calendar.validator import ValidationError, validate_ics
from challenge_radar.definition.models import CanonicalChallenge

from ..conftest import make_config


def _challenge(
    canonical_id: str = "CHINA_FITNESS_DAY_2026",
    availability_start: str = "2026-08-08",
    availability_end: str = "2026-08-08",
    scope_type: str = "regional",
    country_codes: list[str] | None = None,
    sequence: int = 0,
    predicate_human: str = "完成至少20分钟任意锻炼",
    predicate_raw: str = "workout.duration >= 1170",
    title_zh: str = "全民健身日挑战",
) -> CanonicalChallenge:
    return CanonicalChallenge(
        canonical_id=canonical_id,
        title_zh=title_zh,
        availability_start=availability_start,
        availability_end=availability_end,
        alert_dates=["2026-08-07"],
        scope_type=scope_type,
        country_codes=country_codes or ["CN"],
        predicate_human=predicate_human,
        predicate_raw=predicate_raw,
        sources=["current"],
        sequence=sequence,
    )


def test_uid_stable_and_domain():
    config = make_config()
    event = build_event(_challenge(), config)
    assert event is not None
    uid = str(event.get("uid"))
    assert uid == "apple-watch-challenge-CHINA_FITNESS_DAY_2026@watch.example.com"


def test_all_day_exclusive_dtend():
    config = make_config()
    event = build_event(_challenge(), config)
    assert event.get("dtstart").dt == date(2026, 8, 8)
    assert event.get("dtend").dt == date(2026, 8, 9)  # exclusive


def test_multi_day_event():
    config = make_config()
    event = build_event(
        _challenge("NEW_YEAR_2026", availability_start="2026-01-07", availability_end="2026-01-31"),
        config,
    )
    assert event.get("dtstart").dt == date(2026, 1, 7)
    assert event.get("dtend").dt == date(2026, 2, 1)


def test_sequence_written():
    config = make_config()
    event = build_event(_challenge(sequence=3), config)
    assert event.get("sequence") == 3


def test_summary_prefix():
    config = make_config()
    event = build_event(_challenge(), config)
    assert str(event.get("summary")) == "⌚ Apple Watch｜全民健身日挑战"


def test_description_contains_details():
    config = make_config()
    event = build_event(_challenge(), config)
    description = str(event.get("description"))
    assert "完成至少20分钟任意锻炼" in description
    assert "workout.duration >= 1170" in description
    assert "CHINA_FITNESS_DAY_2026" in description
    assert "ActivityChallengeAssets" in description


def test_alarms_present():
    config = make_config()
    event = build_event(_challenge(), config)
    alarms = [c for c in event.subcomponents if c.name == "VALARM"]
    assert len(alarms) == 2


def test_no_availability_skips_event():
    config = make_config()
    event = build_event(_challenge(availability_start=None, availability_end=None), config)
    assert event is None


def test_generator_writes_all_feeds_atomically(tmp_path):
    config = make_config()
    gen = CalendarGenerator(config, output_dir=tmp_path)
    paths = gen.generate_all([_challenge()])
    assert len(paths) == 6
    for name in ("all", "history", "upcoming", "global", "cn", "us"):
        assert (tmp_path / f"{name}.ics").exists()
        assert not (tmp_path / f"{name}.ics.tmp").exists()
    content = (tmp_path / "cn.ics").read_bytes()
    validate_ics(content)
    assert b"CHINA_FITNESS_DAY_2026" in content


def test_validator_rejects_garbage():
    with pytest.raises(ValidationError):
        validate_ics(b"NOT A CALENDAR", expected_events=1)


def test_history_feed_excludes_future(tmp_path):
    config = make_config()
    gen = CalendarGenerator(config, output_dir=tmp_path)
    gen.generate_all([_challenge()])
    history = (tmp_path / "history.ics").read_bytes()
    assert b"CHINA_FITNESS_DAY_2026" not in history


def test_global_feed_excludes_cn_only(tmp_path):
    config = make_config()
    gen = CalendarGenerator(config, output_dir=tmp_path)
    gen.generate_all([_challenge()])
    global_ics = (tmp_path / "global.ics").read_bytes()
    assert b"CHINA_FITNESS_DAY_2026" not in global_ics