"""Current Source adapter: com.apple.MobileAsset.ActivityChallengeAssets.

Confirmed catalog structure (phase-1 scope):
- A Challenge usually ships Definition / Resource / Sticker assets.
- Only assets with ContentTypeIdentifier == "Definition" are processed.
- Real resource URL is __BaseURL + __RelativePath.
- _MeasurementAlgorithm == SHA-1, _Measurement is 20 raw bytes.
- Definition ZIP layout: AssetData/Definition.plist (core payload).
"""

from __future__ import annotations

import logging
import plistlib
import urllib.request
from pathlib import Path
from typing import Any

from ..catalog.fetcher import USER_AGENT
from .base import ChallengeSourceAdapter, RawChallenge

logger = logging.getLogger(__name__)

CONTENT_TYPE_DEFINITION = "Definition"


class ActivityChallengeAssetsAdapter(ChallengeSourceAdapter):
    source_name = "current"
    asset_type = "com.apple.MobileAsset.ActivityChallengeAssets"

    # ---- catalog ----

    def parse_catalog(self, content: bytes) -> list[dict[str, Any]]:
        try:
            root = plistlib.loads(content)
        except Exception as exc:
            raise ValueError(f"current catalog is not a valid plist: {exc}") from exc
        assets = root.get("Assets") if isinstance(root, dict) else None
        if not isinstance(assets, list):
            raise ValueError("current catalog has no 'Assets' list")
        return [a for a in assets if isinstance(a, dict)]

    def list_definition_assets(self, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        definitions = [
            a for a in catalog if a.get("ContentTypeIdentifier") == CONTENT_TYPE_DEFINITION
        ]
        other_types = {
            str(a.get("ContentTypeIdentifier")) for a in catalog if a.get("ContentTypeIdentifier")
        } - {CONTENT_TYPE_DEFINITION}
        if other_types:
            logger.debug("current: skipping asset types %s (phase-1 scope)", sorted(other_types))
        return definitions

    def fingerprint_asset(self, asset: dict[str, Any]) -> str:
        measurement = asset.get("_Measurement")
        if isinstance(measurement, bytes):
            return measurement.hex()
        if isinstance(measurement, str):
            return measurement
        # Fallback: content version + relative path is stable enough.
        return f"v{asset.get('_ContentVersion', '?')}:{asset.get('__RelativePath', '?')}"

    # ---- asset download & parse ----

    def _asset_url(self, asset: dict[str, Any]) -> str:
        base = asset.get("__BaseURL", "")
        rel = asset.get("__RelativePath", "")
        return f"{base}{rel}"

    def _asset_cache_dir(self, asset: dict[str, Any]) -> Path:
        identifier = str(asset.get("DefinitionIdentifier") or "unknown")
        return self.assets_dir / identifier

    def download_asset(self, asset: dict[str, Any]) -> Path:
        url = self._asset_url(asset)
        sha1 = self.fingerprint_asset(asset)
        version = str(asset.get("_ContentVersion") or "0")
        identifier = str(asset.get("DefinitionIdentifier") or "unknown")
        cache_dir = self._asset_cache_dir(asset)
        cache_dir.mkdir(parents=True, exist_ok=True)
        zip_path = cache_dir / f"{version}-{sha1}.zip"
        if zip_path.exists() and zip_path.stat().st_size > 0:
            logger.debug("current: cached %s", zip_path.name)
            return zip_path
        # Download to a temp file then atomically rename (partial downloads
        # must never look like a complete asset).
        tmp_path = zip_path.with_suffix(".zip.tmp")
        logger.info("current: downloading %s (%s)", identifier, url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            tmp_path.write_bytes(resp.read())
        tmp_path.replace(zip_path)
        return zip_path

    def parse_challenge(self, asset: dict[str, Any], bundle: Path) -> RawChallenge:
        definition = self._read_definition_plist(bundle)
        return RawChallenge(
            source=self.source_name,
            identifier=str(asset.get("DefinitionIdentifier") or definition.get("identifier") or "unknown"),
            definition=definition,
            metadata=asset,
            sha1=self.fingerprint_asset(asset),
            download_url=self._asset_url(asset),
            content_version=str(asset.get("_ContentVersion") or definition.get("contentVersion") or None),
            compatibility_version=_as_int(asset.get("_CompatibilityVersion")),
            content_type=CONTENT_TYPE_DEFINITION,
        )

    @staticmethod
    def _read_definition_plist(bundle: Path) -> dict[str, Any]:
        """Locate AssetData/Definition.plist inside the ZIP and parse it."""
        import zipfile

        with zipfile.ZipFile(bundle) as zf:
            candidates: list[str] = []
            for name in zf.namelist():
                if name.rstrip("/").endswith("Definition.plist"):
                    candidates.append(name)
            if not candidates:
                raise ValueError(f"no Definition.plist inside {bundle.name}")
            # Prefer the canonical AssetData/Definition.plist path.
            candidates.sort(key=lambda n: (n != "AssetData/Definition.plist", n))
            raw = zf.read(candidates[0])
        try:
            parsed = plistlib.loads(raw)
        except Exception as exc:
            raise ValueError(f"Definition.plist in {bundle.name} is not a valid plist: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"Definition payload in {bundle.name} is not a dict")
        return parsed


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None