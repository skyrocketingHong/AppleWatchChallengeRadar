"""Human-readable formatting of parsed predicates.

Known patterns map to friendly Chinese descriptions; anything else returns
None so the caller can keep the raw predicate and mark it unparsed.
Duration uses the ~30s Apple tolerance: display_minutes = round((s + 30) / 60).
"""

from __future__ import annotations

import logging

from .parser import Comparison, Expr, Logical, flatten_comparisons, type_or_group
from .workout_types import WorkoutTypeRegistry

logger = logging.getLogger(__name__)

UNKNOWN_HUMAN = "暂未识别的 Apple 挑战条件"


def _display_minutes(seconds: float) -> int:
    return round((seconds + 30) / 60)


def _display_distance(km: float) -> str:
    rounded = round(km)
    if abs(km - rounded) < 0.05:
        return str(rounded)
    return f"{km:.1f}"


def _minutes_text(seconds: float) -> str:
    return f"完成至少{_display_minutes(seconds)}分钟"


def _format_type_suffix(type_ids: list[int], registry: WorkoutTypeRegistry) -> str | None:
    """Type label appended to a duration/distance base.

    A multi-type set collapsing into a group label (e.g. dance) appends
    "锻炼"; other sets join display names without a suffix."""
    if len(type_ids) > 1:
        group = registry.group_label(type_ids)
        if group:
            return f"{group}锻炼"
    return registry.display_names(type_ids)


def _format_single(cmp: Comparison, registry: WorkoutTypeRegistry) -> str | None:
    if cmp.op not in (">=", ">"):
        return None
    if cmp.metric == "workout.duration":
        return f"{_minutes_text(cmp.value)}任意锻炼"
    if cmp.metric == "workout.kilometers":
        return f"完成至少{_display_distance(cmp.value)}公里任意锻炼"
    if cmp.metric == "currentExercisePercentage" and cmp.value >= 1.0:
        return "完成当天锻炼圆环"
    if cmp.metric == "currentStreakForAllActivity":
        return f"连续{int(cmp.value)}天关闭全部活动圆环"
    return None


def _format_and(expr: Logical, registry: WorkoutTypeRegistry) -> str | None:
    duration_cmp: Comparison | None = None
    km_cmp: Comparison | None = None
    type_ids: list[int] | None = None

    for child in expr.children:
        if isinstance(child, Logical) and child.op == "OR":
            ids, is_type = type_or_group(child)
            if is_type:
                type_ids = ids
            continue
        if isinstance(child, Comparison):
            if child.metric == "workout.duration" and child.op in (">=", ">"):
                duration_cmp = child
            elif child.metric == "workout.kilometers" and child.op in (">=", ">"):
                km_cmp = child
            elif child.metric == "workout.type" and child.op == "==":
                type_ids = [int(child.value)]
            else:
                return None

    if duration_cmp is not None:
        base = _minutes_text(duration_cmp.value)
        if type_ids:
            suffix = _format_type_suffix(type_ids, registry)
            if not suffix:
                return None
            return f"{base}{suffix}"
        return f"{base}任意锻炼"
    if km_cmp is not None:
        base = f"完成至少{_display_distance(km_cmp.value)}公里"
        if type_ids:
            suffix = _format_type_suffix(type_ids, registry)
            if not suffix:
                return None
            return f"{base}{suffix}"
        return f"{base}任意锻炼"
    return None


def humanize(ast: Expr, registry: WorkoutTypeRegistry) -> str | None:
    """Format an AST into a human description; None if the pattern is unknown."""
    if isinstance(ast, Logical) and ast.op == "AND":
        return _format_and(ast, registry)
    if isinstance(ast, Comparison):
        return _format_single(ast, registry)
    return None


def humanize_raw(raw: str, registry: WorkoutTypeRegistry) -> tuple[str | None, bool]:
    """Convenience wrapper: returns (human, parsed_ok)."""
    from .parser import parse_predicate

    result = parse_predicate(raw)
    if not result.ok or result.ast is None:
        if raw and raw.strip():
            logger.warning("unknown predicate syntax: %r", raw)
        return None, False
    human = humanize(result.ast, registry)
    if human is None:
        logger.warning("unknown predicate pattern: %r", raw)
        return None, False
    return human, True