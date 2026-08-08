"""Extract typed business fields from a raw Definition payload.

Date fields inside a plist may arrive as datetime objects (plist <date>),
ISO-8601 strings, or numbers. All are normalized to YYYY-MM-DD so the rest of
the pipeline only ever handles plain dates. Semantic meanings of the fields
are preserved verbatim; no inference is performed here.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def normalize_date(value: Any) -> str | None:
    """Normalize a plist date value to YYYY-MM-DD, or None if unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        match = _ISO_DATE_RE.match(text)
        if match:
            return match.group(0)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.date().isoformat()
        except ValueError:
            return None
    return None


def normalize_date_list(value: Any) -> list[str]:
    """Normalize a list of dates; silently drops unparseable entries."""
    if value is None:
        return []
    if isinstance(value, (str, datetime, date, int, float)):
        value = [value]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        norm = normalize_date(item)
        if norm:
            result.append(norm)
    return sorted(set(result))


def normalize_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _get(definition: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in definition and definition[name] is not None:
            return definition[name]
    for key, val in definition.items():
        if key.lower() in {n.lower() for n in names} and val is not None:
            return val
    return None


def extract_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Definition.plist dict onto typed business fields.

    Every field is best-effort; unparseable or missing values become None /
    empty so the canonical model can record them as unknown instead of wrong.
    """
    return {
        "identifier": _get(definition, "identifier"),
        "alert_dates": normalize_date_list(_get(definition, "alertDates")),
        "availability_start": normalize_date(_get(definition, "availabilityStart")),
        "availability_end": normalize_date(_get(definition, "availabilityEnd")),
        "visibility_start": normalize_date(_get(definition, "visibilityStart")),
        "visibility_end": normalize_date(_get(definition, "visibilityEnd")),
        "available_country_codes": normalize_str_list(_get(definition, "availableCountryCodes")),
        "predicate": _get(definition, "predicate"),
        "triggers": _as_int(_get(definition, "triggers")),
        "badge_shape": _get(definition, "badgeShapeName"),
        "display_order": _as_int(_get(definition, "displayOrder")),
    }


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None