"""Single VEVENT construction from a CanonicalChallenge."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from icalendar import Alarm, Event
from icalendar.cal import Component

from ..definition.models import SCOPE_GLOBAL, CanonicalChallenge

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {
    "current": "ActivityChallengeAssets",
    "legacy": "Activity.Achievements",
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _scope_label(challenge: CanonicalChallenge) -> str:
    if challenge.scope_type == SCOPE_GLOBAL:
        return "全球"
    if challenge.scope_type == "regional":
        codes = ",".join(challenge.country_codes) if challenge.country_codes else "未知"
        return f"{codes} 限定"
    return "未知"


def _title(challenge: CanonicalChallenge, config: Any) -> str:
    prefix = config.calendar.get("titlePrefix", "⌚ Apple Watch｜")
    name = challenge.title_zh or challenge.title_en or challenge.canonical_id
    return f"{prefix}{name}"


def _description(challenge: CanonicalChallenge, config: Any) -> str:
    lines = ["Apple Watch 限定健身挑战", ""]
    lines.append("挑战：")
    lines.append(challenge.title_zh or challenge.title_en or challenge.canonical_id)
    lines.append("")
    lines.append("范围：")
    lines.append(_scope_label(challenge))
    lines.append("")
    lines.append("完成条件：")
    lines.append(challenge.predicate_human or "暂未识别的 Apple 挑战条件")
    if challenge.availability_start:
        lines.extend(["", "挑战日期：", challenge.availability_start])
        if challenge.availability_end and challenge.availability_end != challenge.availability_start:
            lines[-1] += f" ~ {challenge.availability_end}"
    if challenge.alert_dates:
        lines.extend(["", "Apple 提醒日期：", "、".join(challenge.alert_dates)])
    if config.calendar.get("includeRawPredicate", True) and challenge.predicate_raw:
        lines.extend(["", "Apple 内部规则：", challenge.predicate_raw])
    lines.extend(["", "Identifier：", challenge.canonical_id])
    source_names = [_SOURCE_LABELS.get(s, s) for s in challenge.sources]
    lines.extend(["", "数据来源：", "、".join(source_names)])
    return "\n".join(lines)


def _add_alarms(event: Event, config: Any) -> None:
    alarms = config.calendar.get("alarms", {})
    if not alarms.get("enabled", True):
        return
    for offset in alarms.get("offsets", ["-P1D", "PT0H"]):
        try:
            delta = _parse_duration(offset)
        except ValueError:
            logger.warning("invalid alarm offset %r ignored", offset)
            continue
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", "Apple Watch 限定健身挑战")
        alarm.add("trigger", delta)
        event.add_component(alarm)


def _parse_duration(value: str) -> timedelta:
    """Parse ISO-8601 duration of the shapes P1D / PT0H / -P1D / -PT30M."""
    text = value.strip()
    negative = False
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if not text.startswith("P"):
        raise ValueError(f"not an ISO duration: {value!r}")
    rest = text[1:]
    days = 0
    seconds = 0.0
    if "T" in rest:
        date_part, time_part = rest.split("T", 1)
    else:
        date_part, time_part = rest, ""
    if date_part:
        stripped = date_part.rstrip("D")
        days = int(stripped) if stripped else 0
    if time_part:
        hours = 0.0
        minutes = 0.0
        secs = 0.0
        buf = ""
        for ch in time_part:
            if ch in "HMS":
                val = float(buf) if buf else 0.0
                if ch == "H":
                    hours = val
                elif ch == "M":
                    minutes = val
                else:
                    secs = val
                buf = ""
            else:
                buf += ch
        seconds = hours * 3600 + minutes * 60 + secs
    delta = timedelta(days=days, seconds=seconds)
    return -delta if negative else delta


def build_event(challenge: CanonicalChallenge, config: Any) -> Component | None:
    """Build a VEVENT; returns None when no usable availability dates exist."""
    start = _parse_date(challenge.availability_start)
    end = _parse_date(challenge.availability_end)
    if start is None:
        logger.warning("ICS skip %s: no availability_start", challenge.canonical_id)
        return None
    if end is None or end < start:
        end = start

    uid = f"apple-watch-challenge-{challenge.canonical_id}@{config.calendar.get('uidDomain', 'watch.example.com')}"

    event = Event()
    event.add("uid", uid)
    event.add("dtstart", start)
    event.add("dtend", end + timedelta(days=1))  # DTEND is exclusive
    event.add("summary", _title(challenge, config))
    event.add("description", _description(challenge, config))
    event.add("sequence", challenge.sequence)
    stamp = datetime.now(timezone.utc)
    event.add("dtstamp", stamp)
    event.add("last-modified", stamp)
    _add_alarms(event, config)
    return event