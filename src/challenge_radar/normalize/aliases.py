"""Alias resolution between Legacy and Current identifiers.

Explicit mapping only: never fuzzy-match names automatically. When Apple data
confirms two identifiers belong to the same challenge, an entry is added to
config/challenge-aliases.yaml. Principle: better to not merge than to merge
incorrectly.
"""

from __future__ import annotations

from typing import Any


class AliasResolver:
    def __init__(self, aliases_config: dict[str, Any] | None = None):
        self._map: dict[str, str] = {}
        for source_id, info in (aliases_config or {}).items():
            if isinstance(info, dict) and info.get("canonical"):
                self._map[str(source_id)] = str(info["canonical"])

    def resolve(self, identifier: str) -> str:
        """Return the canonical identifier for a source identifier."""
        return self._map.get(identifier, identifier)

    def add(self, source_id: str, canonical: str) -> None:
        self._map[source_id] = canonical