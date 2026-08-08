"""Normalizer: map a RawChallenge onto the Canonical Challenge Model.

Rules:
- Missing fields stay NULL / unknown; never guessed (e.g. no country codes is
  NOT global — it is unknown).
- Empty availableCountryCodes means global; a missing key means unknown.
- Titles come from config/challenge-names.yaml by longest identifier prefix;
  unknown identifiers keep the canonical id as-is.
- Predicates are parsed via the AST-lite parser; unparseable ones keep the raw
  text and are marked parsed=false, which must never fail the whole update.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..definition.models import SCOPE_GLOBAL, SCOPE_REGIONAL, SCOPE_UNKNOWN, CanonicalChallenge
from ..definition.parser import extract_definition
from ..predicate.formatter import humanize_raw
from ..predicate.workout_types import WorkoutTypeRegistry
from ..sources.base import RawChallenge
from .aliases import AliasResolver

logger = logging.getLogger(__name__)

_YEAR_SUFFIX_RE = re.compile(r"_(\d{4})$")


class Normalizer:
    def __init__(self, config: Any):
        self.names: dict[str, Any] = config.names or {}
        self.aliases = AliasResolver(config.aliases or {})
        self.registry = WorkoutTypeRegistry(config.workout_types or {})

    def canonical_id(self, raw: RawChallenge) -> str:
        return self.aliases.resolve(raw.identifier)

    def normalize(self, raw: RawChallenge) -> CanonicalChallenge:
        extracted = extract_definition(raw.definition)
        canonical_id = self.canonical_id(raw)

        predicate_raw = extracted.get("predicate")
        if predicate_raw:
            human, parsed = humanize_raw(str(predicate_raw), self.registry)
        else:
            human, parsed = None, False

        scope_type, country_codes = self._resolve_scope(raw.definition, extracted)

        year = self._extract_year(canonical_id, extracted.get("availability_start"))
        title_zh, title_en = self._resolve_title(canonical_id)

        return CanonicalChallenge(
            canonical_id=canonical_id,
            title_zh=title_zh,
            title_en=title_en,
            year=year,
            visibility_start=extracted.get("visibility_start"),
            visibility_end=extracted.get("visibility_end"),
            availability_start=extracted.get("availability_start"),
            availability_end=extracted.get("availability_end"),
            alert_dates=extracted.get("alert_dates") or [],
            scope_type=scope_type,
            country_codes=country_codes,
            predicate_raw=predicate_raw,
            predicate_human=human,
            predicate_parsed=parsed,
            trigger_mask=extracted.get("triggers"),
            badge_shape=extracted.get("badge_shape"),
            display_order=extracted.get("display_order"),
            sources=[raw.source],
            source_records={
                raw.source: {
                    "source_identifier": raw.identifier,
                    "content_version": raw.content_version,
                    "compatibility_version": raw.compatibility_version,
                    "sha1": raw.sha1,
                    "download_url": raw.download_url,
                }
            },
        )

    @staticmethod
    def _resolve_scope(definition: dict[str, Any], extracted: dict[str, Any]) -> tuple[str, list[str]]:
        """Distinguish missing key (unknown) from empty list (global)."""
        # The extracted payload always carries the key; check the raw payload
        # so a missing availableCountryCodes stays unknown, not global.
        has_key = any(
            key.lower() in {"availablecountrycodes", "available_country_codes"} for key in definition
        )
        if not has_key:
            return SCOPE_UNKNOWN, []
        codes = extracted.get("available_country_codes") or []
        if not codes:
            return SCOPE_GLOBAL, []
        return SCOPE_REGIONAL, codes

    @staticmethod
    def _extract_year(canonical_id: str, availability_start: str | None) -> int | None:
        match = _YEAR_SUFFIX_RE.search(canonical_id)
        if match:
            return int(match.group(1))
        if availability_start:
            try:
                return int(availability_start[:4])
            except ValueError:
                return None
        return None

    def _resolve_title(self, canonical_id: str) -> tuple[str | None, str | None]:
        best_key: str | None = None
        for key in self.names:
            if canonical_id.startswith(key) and (best_key is None or len(key) > len(best_key)):
                best_key = key
        if best_key is None:
            return None, None
        info = self.names[best_key]
        if not isinstance(info, dict):
            return None, None
        return info.get("zh"), info.get("en")