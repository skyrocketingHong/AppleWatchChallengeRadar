"""ICS validation performed before atomic rename.

Ensures generated content parses as a calendar and matches expectations so a
corrupt write can never replace a previously good file.
"""

from __future__ import annotations

import logging
from typing import Any

from icalendar import Calendar

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


def validate_ics(content: bytes, expected_events: int | None = None) -> None:
    """Parse ICS bytes and sanity-check structure; raises ValidationError."""
    if not content.startswith(b"BEGIN:VCALENDAR"):
        raise ValidationError("content does not start with BEGIN:VCALENDAR")
    try:
        calendar = Calendar.from_ical(content)
    except Exception as exc:  # noqa: BLE001 - any parse failure is fatal here
        raise ValidationError(f"ICS parse failed: {exc}") from exc
    if expected_events is not None:
        actual = 0
        for component in calendar.walk():
            if component.name == "VEVENT":
                actual += 1
        if actual != expected_events:
            raise ValidationError(
                f"expected {expected_events} VEVENTs, generated {actual}"
            )