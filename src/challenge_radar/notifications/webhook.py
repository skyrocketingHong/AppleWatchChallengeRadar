"""Generic webhook provider: POSTs the event as JSON to a configured URL."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from .base import Notifier, NotificationEvent

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20


class WebhookNotifier(Notifier):
    name = "webhook"

    def __init__(self, config: Any):
        super().__init__(config)
        self.url = (config.provider_config(self.name) or {}).get("url", "")

    def send(self, event: NotificationEvent) -> bool:
        if not self.url:
            logger.warning("webhook notifier enabled but url is empty; skipping")
            return False
        payload = {
            "event": event.event_type,
            "canonical_id": event.canonical_id,
            "title": event.title,
            "scope": event.scope,
            "availability": event.availability,
            "predicate_human": event.predicate_human,
            "sources": event.sources,
            "changes": event.changes,
            "text": event.to_text(),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            resp.read()
        return True