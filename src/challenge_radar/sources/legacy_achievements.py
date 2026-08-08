"""Legacy Source adapter: com.apple.MobileAsset.Activity.Achievements.

The Legacy schema is NOT assumed to mirror the Current one. Phase-1 processing
starts with Schema Discovery (see discover_schema) and only then builds a
tolerant parser. Constraints:
- Never assume DefinitionIdentifier / ContentTypeIdentifier / AssetData layout.
- Missing fields must stay NULL / unknown, never guessed.
- Every asset must finally map onto the Canonical Challenge Model.
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


class LegacyAchievementsAdapter(ChallengeSourceAdapter):
    source_name = "legacy"
    asset_type = "com.apple.MobileAsset.Activity.Achievements"

    # ---- catalog ----

    def parse_catalog(self, content: bytes) -> list[dict[str, Any]]:
        try:
            root = plistlib.loads(content)
        except Exception as exc:
            raise ValueError(f"legacy catalog is not a valid plist: {exc}") from exc
        assets = root.get("Assets") if isinstance(root, dict) else None
        if not isinstance(assets, list):
            raise ValueError("legacy catalog has no 'Assets' list")
        return [a for a in assets if isinstance(a, dict)]

    def list_definition_assets(self, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Legacy schema is discovered, not assumed.

        If the catalog exposes ContentTypeIdentifier we restrict to Definition;
        otherwise we treat every asset as a candidate challenge bundle.
        """
        has_content_type = any("ContentTypeIdentifier" in a for a in catalog)
        if has_content_type:
            definitions = [a for a in catalog if a.get("ContentTypeIdentifier") == "Definition"]
            if definitions:
                return definitions
            logger.warning("legacy: ContentTypeIdentifier present but no Definition assets")
        return catalog

    def fingerprint_asset(self, asset: dict[str, Any]) -> str:
        measurement = asset.get("_Measurement")
        if isinstance(measurement, bytes):
            return measurement.hex()
        if isinstance(measurement, str):
            return measurement
        return f"v{asset.get('_ContentVersion', '?')}:{asset.get('__RelativePath', '?')}"

    # ---- asset download & parse ----

    def _asset_url(self, asset: dict[str, Any]) -> str:
        base = asset.get("__BaseURL", "")
        rel = asset.get("__RelativePath", "")
        return f"{base}{rel}"

    def download_asset(self, asset: dict[str, Any]) -> Path:
        url = self._asset_url(asset)
        sha1 = self.fingerprint_asset(asset)
        version = str(asset.get("_ContentVersion") or "0")
        identifier = str(asset.get("DefinitionIdentifier") or asset.get("identifier") or "unknown")
        cache_dir = self.assets_dir / identifier
        cache_dir.mkdir(parents=True, exist_ok=True)
        zip_path = cache_dir / f"{version}-{sha1}.zip"
        if zip_path.exists() and zip_path.stat().st_size > 0:
            return zip_path
        tmp_path = zip_path.with_suffix(".zip.tmp")
        logger.info("legacy: downloading %s (%s)", identifier, url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            tmp_path.write_bytes(resp.read())
        tmp_path.replace(zip_path)
        return zip_path

    def parse_challenge(self, asset: dict[str, Any], bundle: Path) -> RawChallenge:
        """Tolerant Legacy bundle parsing.

        Scans every top-level plist inside the ZIP and picks the most
        informative dict as the definition payload. Unknown fields stay None.
        """
        definition = self._read_best_plist(bundle)
        identifier = (
            str(asset.get("DefinitionIdentifier") or asset.get("identifier") or "")
            or str(definition.get("identifier") or definition.get("challengeIdentifier") or "")
            or bundle.parent.name
        )
        return RawChallenge(
            source=self.source_name,
            identifier=identifier,
            definition=definition,
            metadata=asset,
            sha1=self.fingerprint_asset(asset),
            download_url=self._asset_url(asset),
            content_version=str(asset.get("_ContentVersion") or None),
            compatibility_version=_as_int(asset.get("_CompatibilityVersion")),
            content_type=str(asset.get("ContentTypeIdentifier") or "Definition"),
        )

    @staticmethod
    def _read_best_plist(bundle: Path) -> dict[str, Any]:
        import zipfile

        with zipfile.ZipFile(bundle) as zf:
            plists: list[tuple[str, bytes]] = []
            for name in zf.namelist():
                if name.rstrip("/").endswith(".plist"):
                    plists.append((name, zf.read(name)))
        if not plists:
            raise ValueError(f"no plist inside legacy bundle {bundle.name}")
        best_name: str | None = None
        best_payload: dict[str, Any] | None = None
        for name, raw in plists:
            try:
                parsed = plistlib.loads(raw)
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            # Prefer payloads that look like a challenge definition.
            score = _definition_score(parsed)
            if best_payload is None or score > _definition_score(best_payload):
                best_name, best_payload = name, parsed
        if best_payload is None:
            raise ValueError(f"no parseable plist dict inside legacy bundle {bundle.name}")
        logger.debug("legacy: definition payload from %s", best_name)
        return best_payload


def _definition_score(payload: dict[str, Any]) -> int:
    """Heuristic: richer, more challenge-like dicts score higher (0..100)."""
    score = 0
    keys = set(payload.keys())
    for key in ("identifier", "challengeIdentifier", "title", "name", "availabilityStart"):
        if key in keys:
            score += 15
    if "predicate" in keys or "completionCriteria" in keys or "activityType" in keys:
        score += 20
    if "AssetData" in keys or "Contents" in keys:
        score += 10
    score += min(len(keys), 20)
    return score


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None