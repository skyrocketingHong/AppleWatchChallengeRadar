"""Workout type registry loaded from config/workout-types.yaml.

Predicate parsing must never hardcode workout type numbers; every lookup goes
through this registry so unknown types degrade gracefully.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Keys whose zh name collapses to a group label when combined.
_DANCE_KEYS = {"dance", "cardioDance", "socialDance"}


class WorkoutTypeRegistry:
    def __init__(self, types_config: dict[str, Any] | None = None):
        self._by_id: dict[int, dict[str, Any]] = {}
        for id_str, info in (types_config or {}).items():
            try:
                type_id = int(id_str)
            except (TypeError, ValueError):
                continue
            if not isinstance(info, dict):
                continue
            self._by_id[type_id] = {
                "id": type_id,
                "key": str(info.get("key", "")),
                "zh": str(info.get("zh", "")),
            }

    def has(self, type_id: int) -> bool:
        return type_id in self._by_id

    def name(self, type_id: int) -> str | None:
        info = self._by_id.get(type_id)
        return info["zh"] if info and info["zh"] else None

    def key(self, type_id: int) -> str | None:
        info = self._by_id.get(type_id)
        return info["key"] if info else None

    def is_dance(self, type_id: int) -> bool:
        key = self.key(type_id)
        return bool(key and key in _DANCE_KEYS)

    def group_label(self, type_ids: list[int]) -> str | None:
        """Collapse a set of types into a group label when appropriate."""
        if not type_ids:
            return None
        if all(self.is_dance(t) for t in type_ids):
            return "舞蹈类"
        return None

    def display_names(self, type_ids: list[int]) -> str:
        """Join display names for a list of types (unknown types noted)."""
        labels: list[str] = []
        for type_id in type_ids:
            name = self.name(type_id)
            if name:
                labels.append(name)
            else:
                logger.warning("unknown workout type id %d in predicate", type_id)
                labels.append(f"类型{type_id}")
        return "或".join(labels)