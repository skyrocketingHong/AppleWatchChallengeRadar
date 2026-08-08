"""Notifier interface and the canonical notification event."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

NEW_CHALLENGE = "NEW_CHALLENGE"
UPDATED_CHALLENGE = "UPDATED_CHALLENGE"
REMOVED_FUTURE_CHALLENGE = "REMOVED_FUTURE_CHALLENGE"

_SOURCE_LABELS = {
    "current": "Apple ActivityChallengeAssets",
    "legacy": "Apple Activity.Achievements",
}


@dataclass
class NotificationEvent:
    event_type: str
    canonical_id: str
    title: str | None = None
    scope: str | None = None
    availability: str | None = None
    predicate_human: str | None = None
    first_seen: str | None = None
    sources: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)  # UPDATED human diffs
    key_salt: str = ""  # UPDATED fingerprint; a real change re-notifies

    def event_key(self) -> str:
        """Dedup key; UPDATED includes a fingerprint so a real change re-notifies."""
        if self.event_type == UPDATED_CHALLENGE:
            return f"UPDATED:{self.canonical_id}:{self.key_salt}"
        return f"{self.event_type}:{self.canonical_id}"

    def source_label(self) -> str:
        return "、".join(_SOURCE_LABELS.get(s, s) for s in self.sources) or "未知"

    def to_text(self) -> str:
        """Human-readable message body shared by all providers."""
        if self.event_type == NEW_CHALLENGE:
            return self._new_text()
        if self.event_type == UPDATED_CHALLENGE:
            return self._updated_text()
        if self.event_type == REMOVED_FUTURE_CHALLENGE:
            return self._removed_text()
        return "Apple Watch Challenge Radar 通知"

    def _new_text(self) -> str:
        lines = ["Apple Watch 新挑战已发现", ""]
        lines.append(self.title or self.canonical_id)
        lines.append(self.canonical_id)
        if self.scope:
            lines.extend(["", f"范围：{self.scope}"])
        if self.availability:
            lines.append(f"日期：{self.availability}")
        if self.predicate_human:
            lines.append(f"条件：{self.predicate_human}")
        if self.first_seen:
            lines.extend(["", f"首次发现：{self.first_seen}"])
        lines.extend(["", f"来源：{self.source_label()}", "", "ICS 已自动更新。"])
        return "\n".join(lines)

    def _updated_text(self) -> str:
        lines = ["Apple Watch 挑战规则已更新", "", self.canonical_id]
        if self.title:
            lines.append(self.title)
        if self.changes:
            lines.extend(["", "变化：", "\n".join(f"· {c}" for c in self.changes)])
        lines.extend(["", "数据来源：Apple MobileAsset", "", "ICS 已同步更新。"])
        return "\n".join(lines)

    def _removed_text(self) -> str:
        lines = ["Apple Watch 未来挑战可能被撤回", "", self.canonical_id]
        if self.title:
            lines.append(self.title)
        if self.availability:
            lines.append(f"原定日期：{self.availability}")
        lines.extend(["", "该挑战已从所有成功获取的数据源中消失。"])
        return "\n".join(lines)


class Notifier(ABC):
    """Provider contract: send one event, return True on success."""

    name: str = "base"

    def __init__(self, config: Any):
        self.config = config

    @abstractmethod
    def send(self, event: NotificationEvent) -> bool:
        """Deliver the event; raise on failure."""