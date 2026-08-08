"""Predicate parser and formatter tests based on document sections 102-108."""

from __future__ import annotations

import pytest

from challenge_radar.predicate.formatter import humanize, humanize_raw
from challenge_radar.predicate.parser import Comparison, Logical, parse_predicate
from challenge_radar.predicate.workout_types import WorkoutTypeRegistry

from ..conftest import make_config

REGISTRY = WorkoutTypeRegistry(make_config().workout_types)


def _human(raw: str) -> str | None:
    human, parsed = humanize_raw(raw, REGISTRY)
    return human if parsed else None


# ---- parser basics ----

def test_parse_simple_duration():
    result = parse_predicate("workout.duration >= 1170")
    assert result.ok
    assert isinstance(result.ast, Comparison)
    assert result.ast.metric == "workout.duration"
    assert result.ast.op == ">="
    assert result.ast.value == 1170


def test_parse_and_with_types():
    result = parse_predicate("workout.kilometers >= 4.98897 AND (workout.type == 37 OR workout.type == 71)")
    assert result.ok
    assert isinstance(result.ast, Logical)
    assert result.ast.op == "AND"
    assert len(result.ast.children) == 2


def test_parse_ampersand_and():
    result = parse_predicate("workout.duration >= 570 && workout.type == 57")
    assert result.ok
    assert isinstance(result.ast, Logical)
    assert result.ast.op == "AND"


def test_parse_unknown_metric_ok():
    result = parse_predicate("someNewMetric >= 123")
    assert result.ok


def test_parse_garbage_fails_gracefully():
    result = parse_predicate("workout.duration ??? 1170")
    assert not result.ok
    assert result.error


def test_parse_empty_fails():
    result = parse_predicate("")
    assert not result.ok


# ---- document expectations (102-108) ----

def test_china_fitness_day_human():
    assert _human("workout.duration >= 1170") == "完成至少20分钟任意锻炼"


def test_running_day_human():
    assert (
        _human("workout.kilometers >= 4.98897 AND (workout.type == 37 OR workout.type == 71)")
        == "完成至少5公里跑步或轮椅跑步"
    )


def test_yoga_day_human():
    assert _human("workout.duration >= 570 && workout.type == 57") == "完成至少10分钟瑜伽"


def test_dance_day_human():
    assert (
        _human("workout.duration >= 1170 AND (workout.type == 14 OR workout.type == 77 OR workout.type == 78)")
        == "完成至少20分钟舞蹈类锻炼"
    )


def test_earth_day_human():
    assert _human("workout.duration >= 1770") == "完成至少30分钟任意锻炼"


def test_heart_month_human():
    assert _human("currentExercisePercentage >= 1.0") == "完成当天锻炼圆环"


def test_new_year_human():
    assert _human("currentStreakForAllActivity >= 7") == "连续7天关闭全部活动圆环"


# ---- unknown handling ----

def test_unknown_predicate_returns_none():
    assert humanize_raw("someNewMetric >= 123", REGISTRY) == (None, False)


def test_unknown_workout_type_still_formats():
    # 99 is not in the registry; the formatter must not crash and keeps going.
    human = _human("workout.duration >= 1170 && workout.type == 99")
    assert human is not None
    assert "类型99" in human


def test_duration_tolerance_rounding():
    # 570s -> 10 min, 1170s -> 20 min, 1770s -> 30 min
    assert _human("workout.duration >= 570") == "完成至少10分钟任意锻炼"
    assert _human("workout.duration >= 1170") == "完成至少20分钟任意锻炼"
    assert _human("workout.duration >= 1770") == "完成至少30分钟任意锻炼"


def test_humanize_ast_direct():
    result = parse_predicate("workout.duration >= 1170")
    assert humanize(result.ast, REGISTRY) == "完成至少20分钟任意锻炼"