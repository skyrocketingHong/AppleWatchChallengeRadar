"""Notification dispatch with dedup.

- Bootstrap mode never sends anything (no historical notification floods).
- Every sent event is recorded in the notifications table; the unique
  event_key prevents re-sending.
- A failed provider does not fail the whole update; errors are logged.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from ..storage.database import Database
from .bark import BarkNotifier
from .base import (
    NEW_CHALLENGE,
    REMOVED_FUTURE_CHALLENGE,
    UPDATED_CHALLENGE,
    Notifier,
    NotificationEvent,
)
from .ntfy import NtfyNotifier
from .webhook import WebhookNotifier

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[Notifier]] = {
    "webhook": WebhookNotifier,
    "bark": BarkNotifier,
    "ntfy": NtfyNotifier,
}


class NotificationManager:
    def __init__(self, config: Any, database: Database):
        self.config = config
        self.database = database
        self.providers = self._build_providers()

    def _build_providers(self) -> list[Notifier]:
        providers: list[Notifier] = []
        for name, cls in _PROVIDERS.items():
            if self.config.is_provider_enabled(name):
                try:
                    providers.append(cls(self.config))
                except Exception as exc:  # noqa: BLE001
                    logger.error("failed to initialize %s notifier: %s", name, exc)
        return providers

    def handle(self, events: Iterable[NotificationEvent], bootstrap: bool = False) -> int:
        """Dispatch events; returns number of notifications actually sent."""
        if not self.config.notifications.get("enabled", True):
            return 0
        sent = 0
        for event in events:
            if not self._event_type_enabled(event.event_type):
                continue
            if bootstrap:
                # Bootstrap: record as sent so post-bootstrap updates never
                # re-announce pre-existing challenges.
                key = event.event_key()
                self.database.record_notification(key, event.canonical_id, event.event_type)
                continue
            key = event.event_key()
            if self.database.notification_exists(key):
                continue
            ok = self._dispatch(event)
            if ok:
                self.database.record_notification(key, event.canonical_id, event.event_type)
                sent += 1
        return sent

    def _event_type_enabled(self, event_type: str) -> bool:
        mapping = {
            NEW_CHALLENGE: "newChallenge",
            UPDATED_CHALLENGE: "updatedChallenge",
            REMOVED_FUTURE_CHALLENGE: "removedFutureChallenge",
        }
        return self.config.notification_event_enabled(mapping.get(event_type, ""))

    def _dispatch(self, event: NotificationEvent) -> bool:
        if not self.providers:
            logger.info("notification enabled but no providers configured; skipping")
            return False
        all_ok = True
        for provider in self.providers:
            try:
                provider.send(event)
                logger.info("notification sent via %s (%s)", provider.name, event.canonical_id)
            except Exception as exc:  # noqa: BLE001
                all_ok = False
                logger.error("%s notification failed for %s: %s", provider.name, event.canonical_id, exc)
        return all_ok