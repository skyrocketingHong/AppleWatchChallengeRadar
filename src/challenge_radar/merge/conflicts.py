"""Source conflict detection between Legacy and Current data.

Conflicts must never be silently overwritten: every detected difference is
logged as WARNING and recorded so operators can audit merges.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..definition.models import CanonicalChallenge

logger = logging.getLogger(__name__)

# Fields that, when they differ between sources, are worth warning about.
_OBSERVED_FIELDS = (
    "availability_start",
    "availability_end",
    "visibility_start",
    "visibility_end",
    "scope_type",
    "country_codes",
    "predicate_raw",
    "trigger_mask",
)


@dataclass
class ConflictWarning:
    canonical_id: str
    field: str
    legacy_value: Any
    current_value: Any

    def describe(self) -> str:
        return (
            f"WARNING source conflict {self.canonical_id} '{self.field}': "
            f"legacy={self.legacy_value!r} current={self.current_value!r}"
        )


def detect_conflicts(
    challenges: list[CanonicalChallenge],
) -> list[ConflictWarning]:
    """Compare per-source challenges for the same canonical id.

    ``challenges`` may contain one entry per source. Only pairwise differences
    against the Current source (when present) are reported; the merge result
    follows the documented priority order instead.
    """
    warnings: list[ConflictWarning] = []
    by_source = {c.sources[0]: c for c in challenges if c.sources}
    current = by_source.get("current")
    legacy = by_source.get("legacy")
    if current is None or legacy is None:
        return warnings

    canonical_id = current.canonical_id
    for field in _OBSERVED_FIELDS:
        lval = getattr(legacy, field)
        cval = getattr(current, field)
        if lval == cval:
            continue
        # Empty-vs-missing style differences have no real conflict.
        if not lval and not cval:
            continue
        warnings.append(
            ConflictWarning(
                canonical_id=canonical_id,
                field=field,
                legacy_value=lval,
                current_value=cval,
            )
        )
    for warning in warnings:
        logger.warning("%s", warning.describe())
    return warnings