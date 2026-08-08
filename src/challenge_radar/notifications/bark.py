"""Bark push provider (iOS): GET https://<server>/<deviceKey>/<title>/<body>."""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from typing import Any

from .base import Notifier, NotificationEvent

logger = logging.getLogger(__name__)

DEFAULT_SERVER = "https://api.day.app"
DEFAULT_TIMEOUT = 20


class BarkNotifier(Notifier):
    name = "bark"

    def __init__(self, config: Any):
        super().__init__(config)
        provider = config.provider_config(self.name) or {}
        self.server = (provider.get("server") or DEFAULT_SERVER).rstrip("/")
        self.device_key = provider.get("deviceKey", "")

    def send(self, event: NotificationEvent) -> bool:
        if not self.device_key:
            logger.warning("bark notifier enabled but deviceKey is empty; skipping")
            return False
        title = event.title or event.canonical_id
        body = event.to_text()
        url = f"{self.server}/{urllib.parse.quote(self.device_key)}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}"
        with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT) as resp:
            resp.read()
        return True