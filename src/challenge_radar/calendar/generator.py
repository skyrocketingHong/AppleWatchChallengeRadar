"""ICS feed generation with atomic writes.

Every feed is written to a .tmp file, flushed to disk, validated, then moved
into place with os.replace. Caddy can thus only ever observe either the old
complete file or the new complete file — never a partial one.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable

from icalendar import Calendar

from ..definition.models import CanonicalChallenge
from .event import build_event
from .feeds import filter_feed
from .validator import ValidationError, validate_ics

logger = logging.getLogger(__name__)

FEED_NAMES = ("all", "history", "upcoming", "global", "cn", "us")


class CalendarGenerator:
    def __init__(self, config: Any, output_dir: Path | None = None):
        self.config = config
        self.output_dir = output_dir or config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(self, challenges: Iterable[CanonicalChallenge]) -> list[Path]:
        """Generate every enabled feed; returns paths of written files."""
        challenges = list(challenges)
        written: list[Path] = []
        for name in FEED_NAMES:
            if not self.config.is_feed_enabled(name):
                continue
            selected = filter_feed(name, challenges, self.config)
            content = self._render_calendar(selected)
            path = self._atomic_write(name, content, len(selected))
            logger.info("%s.ics generated (%d events)", name, len(selected))
            written.append(path)
        return written

    def _render_calendar(self, challenges: list[CanonicalChallenge]) -> bytes:
        calendar = Calendar()
        calendar.add("prodid", "-//apple-watch-challenge-radar//Apple Watch Challenges//ZH_CN")
        calendar.add("version", "2.0")
        calendar.add("calscale", "GREGORIAN")
        for challenge in sorted(challenges, key=lambda c: (c.availability_start or "", c.canonical_id)):
            event = build_event(challenge, self.config)
            if event is not None:
                calendar.add_component(event)
        return calendar.to_ical()

    def _atomic_write(self, feed_name: str, content: bytes, expected_events: int) -> Path:
        final_path = self.output_dir / f"{feed_name}.ics"
        tmp_path = self.output_dir / f"{feed_name}.ics.tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            validate_ics(content, expected_events)
        except ValidationError as exc:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"refusing to publish invalid {feed_name}.ics: {exc}") from exc
        os.replace(tmp_path, final_path)
        return final_path