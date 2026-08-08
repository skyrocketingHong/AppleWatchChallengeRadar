"""Configuration loading for challenge-radar.

Configuration directory resolution order:
1. $CHALLENGE_RADAR_CONFIG_DIR (explicit override)
2. /opt/apple-watch-challenge-radar/config (production layout)
3. <project root>/config (development layout, discovered from package location)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR_ENV = "CHALLENGE_RADAR_CONFIG_DIR"
PROD_CONFIG_DIR = Path("/opt/apple-watch-challenge-radar/config")

CONFIG_FILES = {
    "main": "config.yaml",
    "names": "challenge-names.yaml",
    "aliases": "challenge-aliases.yaml",
    "workout_types": "workout-types.yaml",
}

# Optional environment variable overrides for notification secrets.
# Maps env var name -> (section, key).
ENV_OVERRIDES = {
    "RADAR_WEBHOOK_URL": ("notifications", "providers.webhook.url"),
    "RADAR_BARK_SERVER": ("notifications", "providers.bark.server"),
    "RADAR_BARK_DEVICE_KEY": ("notifications", "providers.bark.deviceKey"),
    "RADAR_NTFY_SERVER": ("notifications", "providers.ntfy.server"),
    "RADAR_NTFY_TOPIC": ("notifications", "providers.ntfy.topic"),
}


class ConfigError(Exception):
    """Raised when configuration cannot be loaded."""


def _deep_set(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    keys = dotted_key.split(".")
    node = data
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def _deep_get(data: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    node: Any = data
    for key in dotted_key.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def find_config_dir() -> Path:
    """Locate the configuration directory, preferring explicit env override."""
    env_dir = os.environ.get(CONFIG_DIR_ENV)
    if env_dir:
        path = Path(env_dir)
        if not path.is_dir():
            raise ConfigError(f"$CHALLENGE_RADAR_CONFIG_DIR points to missing dir: {path}")
        return path

    if PROD_CONFIG_DIR.is_dir():
        return PROD_CONFIG_DIR

    # Development: look for <repo root>/config relative to this package.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config"
        if (candidate / "config.yaml").is_file():
            return candidate
    raise ConfigError(
        "config directory not found; set $CHALLENGE_RADAR_CONFIG_DIR or deploy to /opt/apple-watch-challenge-radar"
    )


class Config:
    """Loaded configuration with defaults for missing keys."""

    def __init__(self, config_dir: Path | None = None, data: dict[str, Any] | None = None):
        if data is not None:
            self._data = data
            self.config_dir = config_dir or Path.cwd()
            return
        self.config_dir = config_dir or find_config_dir()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, fname in CONFIG_FILES.items():
            path = self.config_dir / fname
            if not path.is_file():
                raise ConfigError(f"missing config file: {path}")
            with path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
                data[key] = loaded
        merged: dict[str, Any] = {}
        for key, loaded in data.items():
            if isinstance(loaded, dict):
                merged.update(loaded)
        # Apply env overrides last (highest precedence).
        for env_name, (section, dotted_key) in ENV_OVERRIDES.items():
            value = os.environ.get(env_name)
            if value:
                _deep_set(merged, dotted_key, value)
        return merged

    # ---- typed accessors ----

    def _get(self, dotted_key: str, default: Any = None) -> Any:
        return _deep_get(self._data, dotted_key, default)

    @property
    def sources(self) -> dict[str, Any]:
        return self._get("sources", {})

    @property
    def paths(self) -> dict[str, Any]:
        return self._get("paths", {})

    @property
    def state_dir(self) -> Path:
        return Path(self._get("paths.state", "/var/lib/apple-watch-challenge-radar"))

    @property
    def output_dir(self) -> Path:
        return Path(self._get("paths.output", "/var/www/apple-watch-challenges"))

    @property
    def calendar(self) -> dict[str, Any]:
        return self._get("calendar", {})

    @property
    def feeds(self) -> dict[str, Any]:
        return self._get("feeds", {})

    @property
    def notifications(self) -> dict[str, Any]:
        return self._get("notifications", {})

    @property
    def names(self) -> dict[str, Any]:
        return self._get("names", {})

    @property
    def aliases(self) -> dict[str, Any]:
        return self._get("aliases", {})

    @property
    def workout_types(self) -> dict[str, Any]:
        return self._get("types", {})

    def source_config(self, name: str) -> dict[str, Any]:
        return self._get(f"sources.{name}", {})

    def is_source_enabled(self, name: str) -> bool:
        return bool(self._get(f"sources.{name}.enabled", True))

    def feed_config(self, name: str) -> dict[str, Any]:
        return self._get(f"feeds.{name}", {})

    def is_feed_enabled(self, name: str) -> bool:
        return bool(self._get(f"feeds.{name}.enabled", True))

    def notification_event_enabled(self, event: str) -> bool:
        return bool(self._get(f"notifications.events.{event}", True))

    def provider_config(self, name: str) -> dict[str, Any]:
        return self._get(f"notifications.providers.{name}", {})

    def is_provider_enabled(self, name: str) -> bool:
        return bool(self._get(f"notifications.providers.{name}.enabled", False))