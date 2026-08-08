"""ntfy push provider: POSTs the event text to <server>/<topic>."""

from __future__ import annotations

import logging
import urllib.request
from typing import Any

from .base import Notifier, NotificationEvent

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20


class NtfyNotifier(Notifier):
    name = "ntfy"

    def __init__(self, config: Any):
        super().__init__(config)
        provider = config.provider_config(self.name) or {}
        self.server = (provider.get("server") or "https://ntfy.sh").rstrip("/")
        self.topic = provider.get("topic", "")

    def send(self, event: NotificationEvent) -> bool:
        if not self.topic:
            logger.warning("ntfy notifier enabled but topic is empty; skipping")
            return False
        title = event.title or event.canonical_id
        url = f"{self.server}/{self.topic}"
        req = urllib.request.Request(
            url,
            data=event.to_text().encode("utf-8"),
            method="POST",
            headers={
                "Title": title,
                "Tags": "trophy",
                "Priority": "default",
            },
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            resp.read()
        return True