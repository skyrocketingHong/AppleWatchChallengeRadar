"""Canonical Challenge Model.

Business layers (merge, ICS, notifications) only work with this model. It is
the single source of truth for what a challenge means across both sources.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCOPE_UNKNOWN = "unknown"
SCOPE_GLOBAL = "global"
SCOPE_REGIONAL = "regional"


@dataclass
class CanonicalChallenge:
    canonical_id: str

    title_zh: str | None = None
    title_en: str | None = None

    year: int | None = None

    visibility_start: str | None = None  # YYYY-MM-DD
    visibility_end: str | None = None
    availability_start: str | None = None  # YYYY-MM-DD
    availability_end: str | None = None

    alert_dates: list[str] = field(default_factory=list)

    scope_type: str = SCOPE_UNKNOWN
    country_codes: list[str] = field(default_factory=list)

    predicate_raw: str | None = None
    predicate_human: str | None = None
    predicate_parsed: bool = False

    trigger_mask: int | None = None
    badge_shape: str | None = None
    display_order: int | None = None

    sources: list[str] = field(default_factory=list)

    source_records: dict[str, dict[str, Any]] = field(default_factory=dict)

    first_seen: str | None = None
    last_seen: str | None = None
    updated_at: str | None = None
    sequence: int = 0
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalChallenge":
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def business_fingerprint(self) -> str:
        """Fingerprint over business fields only (drives UPDATED detection)."""
        parts = [
            self.availability_start,
            self.availability_end,
            self.visibility_start,
            self.visibility_end,
            self.scope_type,
            ",".join(sorted(self.country_codes)),
            self.predicate_raw,
            str(self.trigger_mask) if self.trigger_mask is not None else "",
            self.badge_shape,
        ]
        return "|".join(p or "" for p in parts)