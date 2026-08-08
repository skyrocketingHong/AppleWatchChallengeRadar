"""Feed filtering rules for the six published ICS calendars."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..definition.models import SCOPE_GLOBAL, CanonicalChallenge

logger = logging.getLogger(__name__)


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _has_region(challenge: CanonicalChallenge, region: str) -> bool:
    return region in challenge.country_codes


def _include_global(config: Any, feed_name: str) -> bool:
    return bool(config.feed_config(feed_name).get("includeGlobal", True))


def filter_feed(name: str, challenges: list[CanonicalChallenge], config: Any) -> list[CanonicalChallenge]:
    """Return the challenges that belong in the named feed."""
    today = today_utc()

    if name == "all":
        return list(challenges)

    if name == "history":
        return [c for c in challenges if c.availability_end and c.availability_end < today]

    if name == "upcoming":
        return [c for c in challenges if not c.availability_end or c.availability_end >= today]

    if name == "global":
        return [c for c in challenges if c.scope_type == SCOPE_GLOBAL]

    if name in ("cn", "us"):
        regions = config.feed_config(name).get("regions", [name.upper()])
        include_global = _include_global(config, name)
        result: list[CanonicalChallenge] = []
        for challenge in challenges:
            if challenge.scope_type == SCOPE_GLOBAL:
                if include_global:
                    result.append(challenge)
            elif challenge.scope_type == "regional" and any(
                _has_region(challenge, region) for region in regions
            ):
                result.append(challenge)
            # unknown scope is never included
        return result

    logger.warning("unknown feed %r; returning empty", name)
    return []