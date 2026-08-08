"""Unified Challenge Source Adapter interface.

Business layers only ever depend on this interface and must not know the
specific Apple schema of either source. Each Apple source gets its own
adapter; it is forbidden to parse the Legacy source with the Current schema.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..catalog.fetcher import CatalogFetcher, FetchResult

logger = logging.getLogger(__name__)


@dataclass
class RawChallenge:
    """Result of parsing one Challenge Definition from one source.

    ``definition`` keeps the source-specific raw payload; normalization later
    maps it onto the Canonical Challenge Model without guessing missing fields.
    """

    source: str
    identifier: str
    definition: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    sha1: str | None = None
    download_url: str | None = None
    content_version: str | None = None
    compatibility_version: int | None = None
    content_type: str | None = None


class ChallengeSourceAdapter(ABC):
    """Contract implemented by LegacyAchievementsAdapter and ActivityChallengeAssetsAdapter."""

    source_name: str = ""
    asset_type: str = ""

    def __init__(self, config: Any, state_dir: Path):
        self.config = config
        self.state_dir = state_dir
        self.source_config = config.source_config(self.source_name)
        self.catalog_url = self.source_config.get("catalogUrl", "")
        self.catalog_dir = state_dir / "catalogs" / self.source_name
        self.assets_dir = state_dir / "assets" / self.source_name
        self._fetcher = CatalogFetcher(self.catalog_dir)
        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    # ---- catalog ----

    def fetch_catalog(self) -> FetchResult:
        """Download the catalog and persist current/previous snapshots."""
        result = self._fetcher.fetch(self.catalog_url)
        if result.ok and result.content:
            self._fetcher.save_snapshot(result.content)
        return result

    @abstractmethod
    def parse_catalog(self, content: bytes) -> list[dict[str, Any]]:
        """Parse catalog bytes into a list of asset metadata dicts."""

    @abstractmethod
    def list_definition_assets(self, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter catalog to the assets that represent Challenge Definitions."""

    @abstractmethod
    def fingerprint_asset(self, asset: dict[str, Any]) -> str:
        """Stable fingerprint for a definition asset (SHA-1 when available)."""

    def asset_key(self, asset: dict[str, Any]) -> tuple[str, str]:
        """(source_identifier, content_type) key; content_type defaults to 'Definition'."""
        identifier = str(asset.get("DefinitionIdentifier") or asset.get("identifier") or "")
        content_type = str(asset.get("ContentTypeIdentifier") or "Definition")
        return (identifier, content_type)

    # ---- asset download & parse ----

    @abstractmethod
    def download_asset(self, asset: dict[str, Any]) -> Path:
        """Download the asset bundle ZIP into the per-source assets dir."""

    @abstractmethod
    def parse_challenge(self, asset: dict[str, Any], bundle: Path) -> RawChallenge:
        """Extract a RawChallenge from a downloaded bundle."""

    # ---- schema discovery (Legacy first phase) ----

    def discover_schema(self) -> dict[str, Any]:
        """Inspect the current local catalog and report observed structure.

        The Legacy adapter must run Schema Discovery before assuming any
        DefinitionIdentifier / ContentTypeIdentifier / AssetData layout.
        """
        content = self._fetcher.read_local(self.catalog_dir)
        if content is None:
            return {"status": "no-catalog"}
        try:
            assets = self.parse_catalog(content)
        except Exception as exc:  # noqa: BLE001 - discovery must not crash
            return {"status": "parse-failed", "error": str(exc)}
        return self._discover(assets)

    def _discover(self, assets: list[dict[str, Any]]) -> dict[str, Any]:
        root_keys: set[str] = set()
        asset_keys: set[str] = set()
        content_types: set[str] = set()
        sample: list[dict[str, Any]] = []
        for asset in assets:
            for key in asset:
                asset_keys.add(str(key))
            for key in asset.get("_Assets", []):
                if isinstance(key, dict):
                    asset_keys.add(str(key))
            ct = asset.get("ContentTypeIdentifier")
            if ct:
                content_types.add(str(ct))
            if len(sample) < 5:
                sample.append(asset)
        return {
            "status": "ok",
            "asset_count": len(assets),
            "root_keys": sorted(root_keys),
            "asset_keys": sorted(asset_keys),
            "content_types": sorted(content_types),
            "sample": sample,
        }