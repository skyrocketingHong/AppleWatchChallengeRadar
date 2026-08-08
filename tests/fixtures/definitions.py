"""2026 challenge definition fixtures (document section 101-108).

Each fixture mirrors the confirmed Current Definition layout inside a ZIP:
AssetData/Definition.plist. Files are generated on demand so tests control
versions and mutations precisely.
"""

from __future__ import annotations

import io
import plistlib
import zipfile
from datetime import datetime, timezone
from typing import Any

CHINA_FITNESS_DAY_2026: dict[str, Any] = {
    "identifier": "CHINA_FITNESS_DAY_2026",
    "alertDates": [datetime(2026, 8, 7, tzinfo=timezone.utc)],
    "availabilityStart": datetime(2026, 8, 8, tzinfo=timezone.utc),
    "availabilityEnd": datetime(2026, 8, 8, tzinfo=timezone.utc),
    "visibilityStart": datetime(2026, 8, 6, tzinfo=timezone.utc),
    "visibilityEnd": datetime(2026, 8, 8, tzinfo=timezone.utc),
    "availableCountryCodes": ["CN"],
    "predicate": "workout.duration >= 1170",
    "triggers": 2,
    "badgeShapeName": "circle",
    "displayOrder": 89,
}

RUNNING_DAY_2026: dict[str, Any] = {
    "identifier": "RUNNING_DAY_2026",
    "alertDates": [datetime(2026, 6, 2, tzinfo=timezone.utc)],
    "availabilityStart": datetime(2026, 6, 3, tzinfo=timezone.utc),
    "availabilityEnd": datetime(2026, 6, 3, tzinfo=timezone.utc),
    "visibilityStart": datetime(2026, 6, 1, tzinfo=timezone.utc),
    "visibilityEnd": datetime(2026, 6, 3, tzinfo=timezone.utc),
    "availableCountryCodes": [],
    "predicate": "workout.kilometers >= 4.98897 AND (workout.type == 37 OR workout.type == 71)",
    "triggers": 2,
    "badgeShapeName": "circle",
    "displayOrder": 40,
}

YOGA_DAY_2026: dict[str, Any] = {
    "identifier": "YOGA_DAY_2026",
    "alertDates": [datetime(2026, 6, 20, tzinfo=timezone.utc)],
    "availabilityStart": datetime(2026, 6, 21, tzinfo=timezone.utc),
    "availabilityEnd": datetime(2026, 6, 21, tzinfo=timezone.utc),
    "visibilityStart": datetime(2026, 6, 19, tzinfo=timezone.utc),
    "visibilityEnd": datetime(2026, 6, 21, tzinfo=timezone.utc),
    "availableCountryCodes": [],
    "predicate": "workout.duration >= 570 && workout.type == 57",
    "triggers": 2,
    "badgeShapeName": "circle",
    "displayOrder": 45,
}

DANCE_DAY_2026: dict[str, Any] = {
    "identifier": "DANCE_DAY_2026",
    "alertDates": [datetime(2026, 4, 28, tzinfo=timezone.utc)],
    "availabilityStart": datetime(2026, 4, 29, tzinfo=timezone.utc),
    "availabilityEnd": datetime(2026, 4, 29, tzinfo=timezone.utc),
    "visibilityStart": datetime(2026, 4, 27, tzinfo=timezone.utc),
    "visibilityEnd": datetime(2026, 4, 29, tzinfo=timezone.utc),
    "availableCountryCodes": [],
    "predicate": "workout.duration >= 1170 AND (workout.type == 14 OR workout.type == 77 OR workout.type == 78)",
    "triggers": 2,
    "badgeShapeName": "circle",
    "displayOrder": 35,
}

EARTH_DAY_2026: dict[str, Any] = {
    "identifier": "EARTH_DAY_2026",
    "alertDates": [datetime(2026, 4, 21, tzinfo=timezone.utc)],
    "availabilityStart": datetime(2026, 4, 22, tzinfo=timezone.utc),
    "availabilityEnd": datetime(2026, 4, 22, tzinfo=timezone.utc),
    "visibilityStart": datetime(2026, 4, 20, tzinfo=timezone.utc),
    "visibilityEnd": datetime(2026, 4, 22, tzinfo=timezone.utc),
    "availableCountryCodes": [],
    "predicate": "workout.duration >= 1770",
    "triggers": 2,
    "badgeShapeName": "circle",
    "displayOrder": 30,
}

HEART_MONTH_2026: dict[str, Any] = {
    "identifier": "HEART_MONTH_2026",
    "alertDates": [datetime(2026, 2, 13, tzinfo=timezone.utc)],
    "availabilityStart": datetime(2026, 2, 14, tzinfo=timezone.utc),
    "availabilityEnd": datetime(2026, 2, 14, tzinfo=timezone.utc),
    "visibilityStart": datetime(2026, 2, 12, tzinfo=timezone.utc),
    "visibilityEnd": datetime(2026, 2, 14, tzinfo=timezone.utc),
    "availableCountryCodes": [],
    "predicate": "currentExercisePercentage >= 1.0",
    "triggers": 16,
    "badgeShapeName": "heart",
    "displayOrder": 10,
}

NEW_YEAR_2026: dict[str, Any] = {
    "identifier": "NEW_YEAR_2026",
    "alertDates": [datetime(2026, 1, 6, tzinfo=timezone.utc)],
    "availabilityStart": datetime(2026, 1, 7, tzinfo=timezone.utc),
    "availabilityEnd": datetime(2026, 1, 31, tzinfo=timezone.utc),
    "visibilityStart": datetime(2025, 12, 28, tzinfo=timezone.utc),
    "visibilityEnd": datetime(2026, 1, 31, tzinfo=timezone.utc),
    "availableCountryCodes": [],
    "predicate": "currentStreakForAllActivity >= 7",
    "triggers": 64,
    "badgeShapeName": "circle",
    "displayOrder": 5,
}

ALL_2026_FIXTURES: dict[str, dict[str, Any]] = {
    "CHINA_FITNESS_DAY_2026": CHINA_FITNESS_DAY_2026,
    "RUNNING_DAY_2026": RUNNING_DAY_2026,
    "YOGA_DAY_2026": YOGA_DAY_2026,
    "DANCE_DAY_2026": DANCE_DAY_2026,
    "EARTH_DAY_2026": EARTH_DAY_2026,
    "HEART_MONTH_2026": HEART_MONTH_2026,
    "NEW_YEAR_2026": NEW_YEAR_2026,
}


def make_definition(code: str, **overrides: Any) -> dict[str, Any]:
    """Return a definition dict for the fixture, mutated by overrides."""
    base = ALL_2026_FIXTURES[code]
    definition = dict(base)
    definition.update(overrides)
    return definition


def make_bundle(definition: dict[str, Any]) -> bytes:
    """Build the canonical Definition ZIP bytes from a definition dict."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AssetData/Definition.plist", plistlib.dumps(definition))
        zf.writestr("AssetData/CompatibilityVersion.plist", plistlib.dumps({"CompatibilityVersion": 3}))
        zf.writestr("Info.plist", plistlib.dumps({"CFBundleIdentifier": definition["identifier"]}))
        zf.writestr("META-INF/com.apple.ZipMetadata.plist", plistlib.dumps({}))
    return buffer.getvalue()


def make_catalog(assets: list[dict[str, Any]]) -> bytes:
    """Build a MobileAsset catalog plist from asset metadata dicts."""
    return plistlib.dumps({"Assets": assets, "AssetType": "com.apple.MobileAsset.ActivityChallengeAssets"})


def make_asset(
    identifier: str,
    content_type: str = "Definition",
    content_version: str = "2",
    sha1_hex: str = "a" * 40,
    relative_path: str = "CHINA_FITNESS_DAY_2026.zip",
    base_url: str = "https://example.invalid/assets/",
) -> dict[str, Any]:
    return {
        "AssetType": "com.apple.MobileAsset.ActivityChallengeAssets",
        "Build": "1",
        "ContentTypeIdentifier": content_type,
        "DefinitionIdentifier": identifier,
        "_CompatibilityVersion": 3,
        "_ContentVersion": content_version,
        "_CompressionAlgorithm": "zip",
        "_DownloadSize": 1234,
        "_UnarchivedSize": 5678,
        "_Measurement": bytes.fromhex(sha1_hex),
        "_MeasurementAlgorithm": "SHA-1",
        "__BaseURL": base_url,
        "__RelativePath": relative_path,
    }