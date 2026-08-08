"""Shared pytest fixtures: config factory and programmable fake adapter."""

from __future__ import annotations

import hashlib
import plistlib
from pathlib import Path
from typing import Any

import pytest

from challenge_radar.catalog.fetcher import FetchResult
from challenge_radar.sources.challenge_assets import ActivityChallengeAssetsAdapter

from .fixtures.definitions import make_asset, make_bundle, make_catalog


def make_config(data: dict[str, Any] | None = None) -> Any:
    """Build a Config-like object from a dict (no filesystem access)."""
    from challenge_radar.config import Config

    defaults: dict[str, Any] = {
        "sources": {
            "legacy": {
                "enabled": True,
                "sourceName": "legacy",
                "assetType": "com.apple.MobileAsset.Activity.Achievements",
                "catalogUrl": "https://mesu.apple.com/legacy.xml",
            },
            "current": {
                "enabled": True,
                "sourceName": "current",
                "assetType": "com.apple.MobileAsset.ActivityChallengeAssets",
                "catalogUrl": "https://mesu.apple.com/current.xml",
            },
        },
        "paths": {"state": "/tmp/nonexistent", "output": "/tmp/nonexistent"},
        "calendar": {
            "language": "zh-CN",
            "titlePrefix": "⌚ Apple Watch｜",
            "uidDomain": "watch.example.com",
            "includeRawPredicate": True,
            "alarms": {"enabled": True, "offsets": ["-P1D", "PT0H"]},
        },
        "feeds": {
            "all": {"enabled": True},
            "history": {"enabled": True},
            "upcoming": {"enabled": True},
            "global": {"enabled": True},
            "cn": {"enabled": True, "includeGlobal": True, "regions": ["CN"]},
            "us": {"enabled": True, "includeGlobal": True, "regions": ["US"]},
        },
        "notifications": {
            "enabled": True,
            "events": {
                "newChallenge": True,
                "updatedChallenge": True,
                "removedFutureChallenge": True,
            },
            "providers": {
                "webhook": {"enabled": False, "url": ""},
                "bark": {"enabled": False, "server": "", "deviceKey": ""},
                "ntfy": {"enabled": False, "server": "", "topic": ""},
            },
        },
        "names": {
            "CHINA_FITNESS_DAY": {"zh": "全民健身日挑战", "en": "National Fitness Day Challenge"},
            "RUNNING_DAY": {"zh": "全球跑步日挑战", "en": "Global Running Day Challenge"},
            "YOGA_DAY": {"zh": "国际瑜伽日挑战", "en": "International Day of Yoga Challenge"},
            "DANCE_DAY": {"zh": "国际舞蹈日挑战", "en": "International Dance Day Challenge"},
            "EARTH_DAY": {"zh": "地球日挑战", "en": "Earth Day Challenge"},
            "HEART_MONTH": {"zh": "心脏月挑战", "en": "Heart Month Challenge"},
            "NEW_YEAR": {"zh": "新年圆环挑战", "en": "Ring in the New Year"},
        },
        "aliases": {},
        "types": {
            "14": {"key": "dance", "zh": "舞蹈"},
            "37": {"key": "running", "zh": "跑步"},
            "57": {"key": "yoga", "zh": "瑜伽"},
            "71": {"key": "wheelchairRunPace", "zh": "轮椅跑步"},
            "77": {"key": "cardioDance", "zh": "有氧舞蹈"},
            "78": {"key": "socialDance", "zh": "社交舞蹈"},
        },
    }
    if data:
        _deep_merge(defaults, data)
    return Config(data=defaults)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


class FakeCurrentAdapter(ActivityChallengeAssetsAdapter):
    """Programmable Current adapter backed by in-memory definitions."""

    source_name = "current"

    def __init__(
        self,
        config: Any,
        state_dir: Path,
        definitions: dict[str, dict[str, Any]] | None = None,
        fetch_failure: str | None = None,
        corrupt_zip: set[str] | None = None,
    ):
        super().__init__(config, state_dir)
        self._definitions = definitions or {}
        self._fetch_failure = fetch_failure
        self._corrupt_zip = corrupt_zip or set()
        self.download_calls: list[str] = []

    def fetch_catalog(self) -> FetchResult:
        if self._fetch_failure:
            return FetchResult(ok=False, status="FETCH_FAILED", error=self._fetch_failure)
        # SHA-1 derived from definition content: a content change naturally
        # changes the fingerprint, mirroring real MobileAsset version bumps.
        assets = [
            make_asset(
                identifier,
                content_version="2",
                sha1_hex=hashlib.sha1(plistlib.dumps(self._definitions[identifier])).hexdigest(),
                relative_path=f"{identifier}.zip",
            )
            for identifier in sorted(self._definitions)
        ]
        return FetchResult(ok=True, status="FETCH_SUCCESS", content=make_catalog(assets))

    def download_asset(self, asset: dict[str, Any]) -> Path:
        identifier = str(asset["DefinitionIdentifier"])
        self.download_calls.append(identifier)
        zip_path = self.assets_dir / identifier / "2-0000000000000000000000000000000000000000.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        if identifier in self._corrupt_zip:
            zip_path.write_bytes(b"not a zip")
        else:
            zip_path.write_bytes(make_bundle(self._definitions[identifier]))
        return zip_path


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "www"


@pytest.fixture
def config_factory() -> Any:
    return make_config