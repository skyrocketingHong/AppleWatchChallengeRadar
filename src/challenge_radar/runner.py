"""Core pipeline: fetch -> diff -> download -> normalize -> merge -> store ->
notify -> generate ICS. Implements bootstrap and incremental update modes with
strict source failure isolation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .calendar.generator import CalendarGenerator
from .catalog.diff import FETCH_FAILED, PARSE_FAILED, SourceDiffResult, diff_assets
from .definition.models import SCOPE_GLOBAL, CanonicalChallenge
from .merge.merger import merge_challenges
from .normalize.normalizer import Normalizer
from .notifications.base import (
    NEW_CHALLENGE,
    REMOVED_FUTURE_CHALLENGE,
    UPDATED_CHALLENGE,
    NotificationEvent,
)
from .notifications.manager import NotificationManager
from .sources.base import ChallengeSourceAdapter, RawChallenge
from .sources.challenge_assets import ActivityChallengeAssetsAdapter
from .sources.legacy_achievements import LegacyAchievementsAdapter
from .storage.database import Database, utc_now
from .storage.history import fingerprint_dict, latest_fingerprint, record_history

logger = logging.getLogger(__name__)

STATE_BOOTSTRAP = "bootstrap_completed"
STATE_LAST_SUCCESS = "last_successful_update"
STATE_LAST_LEGACY = "last_legacy_success"
STATE_LAST_CURRENT = "last_current_success"

_ADAPTERS: dict[str, type[ChallengeSourceAdapter]] = {
    "current": ActivityChallengeAssetsAdapter,
    "legacy": LegacyAchievementsAdapter,
}


@dataclass
class UpdateReport:
    bootstrap: bool
    source_results: dict[str, SourceDiffResult] = field(default_factory=dict)
    new_challenges: list[str] = field(default_factory=list)
    updated_challenges: list[str] = field(default_factory=list)
    removed_future: list[str] = field(default_factory=list)
    notifications_sent: int = 0
    ics_files: list[Path] = field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        config: Any,
        state_dir: Path | None = None,
        output_dir: Path | None = None,
        adapters: dict[str, ChallengeSourceAdapter] | None = None,
    ):
        self.config = config
        self.state_dir = state_dir or config.state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = output_dir or config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.state_dir / "challenges.db")
        self.db.init_schema()
        self.normalizer = Normalizer(config)
        self.adapters = adapters if adapters is not None else self._build_adapters()
        self.generator = CalendarGenerator(config, self.output_dir)
        self.notifier = NotificationManager(config, self.db)

    def close(self) -> None:
        self.db.close()

    def _build_adapters(self) -> dict[str, ChallengeSourceAdapter]:
        adapters: dict[str, ChallengeSourceAdapter] = {}
        for name, cls in _ADAPTERS.items():
            if self.config.is_source_enabled(name):
                try:
                    adapters[name] = cls(self.config, self.state_dir)
                except Exception as exc:  # noqa: BLE001
                    logger.error("failed to initialize %s adapter: %s", name, exc)
        return adapters

    # ---- public entry points ----

    def bootstrap(self) -> UpdateReport:
        """First-time full import; never sends historical notifications."""
        report = self._run(bootstrap=True)
        self.db.set_state(STATE_BOOTSTRAP, "true")
        return report

    def update(self) -> UpdateReport:
        """Incremental update; sends notifications only after bootstrap."""
        bootstrap = self.db.get_state(STATE_BOOTSTRAP) != "true"
        if bootstrap:
            logger.info("bootstrap not completed yet; running bootstrap semantics")
        return self._run(bootstrap=bootstrap)

    def generate(self) -> list[Path]:
        """Regenerate all ICS from the database only (no network access)."""
        return self.generator.generate_all(self._load_active_challenges())

    # ---- pipeline ----

    def _run(self, bootstrap: bool) -> UpdateReport:
        report = UpdateReport(bootstrap=bootstrap)
        now = utc_now()

        raw_by_canonical: dict[str, list[RawChallenge]] = {}
        successful_sources: set[str] = set()
        catalog_keys: dict[str, set[tuple[str, str]]] = {}

        for name, adapter in self.adapters.items():
            result, raws, keys = self._process_source(adapter)
            report.source_results[name] = result
            if result.ok:
                successful_sources.add(name)
                catalog_keys[name] = keys
                self.db.set_state(f"last_{name}_success", now)
                for canonical_id, raw in raws:
                    raw_by_canonical.setdefault(canonical_id, []).append(raw)

        # Merge identical canonical ids across sources (Current preferred).
        merged: dict[str, CanonicalChallenge] = {}
        for canonical_id, raws in raw_by_canonical.items():
            normalized = [self.normalizer.normalize(raw) for raw in raws]
            merged[canonical_id] = merge_challenges(normalized)

        # Snapshot pre-persist state so the canonical diff can tell NEW from
        # UPDATED after this round's rows are written.
        existing = {row["canonical_id"]: row for row in self.db.fetch_all_challenges(active_only=False)}

        # Persist within one transaction; collects removed future challenges.
        removed_future = self._persist(merged, now, successful_sources, catalog_keys, existing)

        # Canonical diff -> notification events.
        events = self._canonical_diff(merged, removed_future, report, existing)

        # Notifications (bootstrap records dedup keys but never sends).
        report.notifications_sent = self.notifier.handle(events, bootstrap=bootstrap)

        # ICS only when something changed (or during bootstrap).
        if report.new_challenges or report.updated_challenges or report.removed_future or bootstrap:
            report.ics_files = self.generator.generate_all(self._load_active_challenges())

        self.db.set_state(STATE_LAST_SUCCESS, now)
        return report

    def _process_source(
        self,
        adapter: ChallengeSourceAdapter,
    ) -> tuple[SourceDiffResult, list[tuple[str, RawChallenge]], set[tuple[str, str]]]:
        """Fetch, parse, diff and download one source. Failure never poisons
        the other source or the existing database state.

        Returns the source diff, newly parsed challenges, and the full set of
        (identifier, content_type) keys present in the catalog (drives the
        seen/removed asset bookkeeping)."""
        name = adapter.source_name
        logger.info("fetching %s catalog: %s", name, adapter.catalog_url)
        fetch = adapter.fetch_catalog()
        if not fetch.ok or fetch.content is None:
            logger.error("%s source fetch failed: %s", name, fetch.error)
            return SourceDiffResult(source=name, status=FETCH_FAILED, error=fetch.error), [], set()

        try:
            catalog = adapter.parse_catalog(fetch.content)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s catalog parse failed: %s", name, exc)
            return SourceDiffResult(source=name, status=PARSE_FAILED, error=str(exc)), [], set()

        definitions = adapter.list_definition_assets(catalog)
        logger.info("%s: %d definitions discovered", name, len(definitions))

        current_map: dict[str, str] = {}
        assets_by_key: dict[str, dict[str, Any]] = {}
        all_keys: set[tuple[str, str]] = set()
        for asset in definitions:
            identifier, content_type = adapter.asset_key(asset)
            if not identifier:
                continue
            key = f"{identifier}:{content_type}"
            all_keys.add((identifier, content_type))
            current_map[key] = adapter.fingerprint_asset(asset)
            assets_by_key[key] = asset

        diff = diff_assets(name, self._previous_asset_map(name), current_map)

        raws: list[tuple[str, RawChallenge]] = []
        for key, status in diff.changes.items():
            if status not in ("NEW", "UPDATED"):
                continue
            asset = assets_by_key.get(key)
            if asset is None:
                continue
            identifier = key.split(":", 1)[0]
            try:
                bundle = adapter.download_asset(asset)
                raw = adapter.parse_challenge(asset, bundle)
            except Exception as exc:  # noqa: BLE001
                # Kept pending: already discovered, downloaded next round.
                logger.error("%s definition download/parse failed for %s: %s", name, identifier, exc)
                continue
            logger.info("definition downloaded: %s (%s)", identifier, name)
            raws.append((self.normalizer.canonical_id(raw), raw))
        return diff, raws, all_keys

    def _previous_asset_map(self, source: str) -> dict[str, str]:
        """Existing asset fingerprints from the DB for one source."""
        result: dict[str, str] = {}
        for row in self.db.fetch_source_assets(source):
            identifier = row["source_identifier"] or ""
            content_type = row["content_type"] or "Definition"
            result[f"{identifier}:{content_type}"] = row["sha1"] or ""
        return result

    # ---- persistence ----

    def _persist(
        self,
        merged: dict[str, CanonicalChallenge],
        now: str,
        successful_sources: set[str],
        catalog_keys: dict[str, set[tuple[str, str]]],
        existing: dict[str, Any],
    ) -> list[str]:
        """Write everything in one transaction; returns removed future ids.

        ``existing`` is the pre-persist snapshot of the challenges table used
        to decide first_seen and sequence."""
        removed_future: list[str] = []
        today = datetime.now(timezone.utc).date().isoformat()

        with self.db.transaction() as conn:
            for canonical_id, challenge in merged.items():
                row = existing.get(canonical_id)
                if row is None or not row["active"]:
                    challenge.first_seen = now
                    challenge.last_seen = now
                    challenge.updated_at = now
                    challenge.sequence = 0
                else:
                    challenge.first_seen = row["first_seen"] or now
                    challenge.last_seen = now
                    challenge.updated_at = now
                    # sequence bumps only on real business changes
                    same = _row_business_fp(row) == challenge.business_fingerprint()
                    challenge.sequence = int(row["sequence"] or 0) if same else int(row["sequence"] or 0) + 1
                challenge.active = True
                self.db.upsert_challenge(conn, _challenge_row(challenge))

                for source, record in challenge.source_records.items():
                    fp = fingerprint_dict(record)
                    if latest_fingerprint(conn, canonical_id, source) != fp:
                        record_history(conn, canonical_id, source, challenge.to_dict(), fingerprint=fp)
                    self._upsert_source_asset_row(conn, source, challenge, record)

            # Only mark assets seen/removed for sources that fully succeeded.
            # The seen set is the full catalog key set, so an unchanged catalog
            # never falsely marks live assets as removed.
            for source in successful_sources:
                seen_keys = catalog_keys.get(source, set())
                self.db.mark_assets_seen(conn, source, seen_keys)
                self.db.mark_assets_removed(conn, source, seen_keys)

            # Deactivate challenges that no longer appear in any successful
            # source's catalog. The check is based on the source_assets rows
            # (already seen/removed-updated above), not on this round's merged
            # set, so an unchanged catalog never falsely deactivates anything.
            if successful_sources:
                placeholders = ",".join("?" for _ in successful_sources)
                rows = conn.execute(
                    f"""
                    SELECT c.canonical_id AS canonical_id,
                           c.availability_start AS availability_start
                    FROM challenges c
                    WHERE c.active = 1
                      AND NOT EXISTS (
                          SELECT 1 FROM source_assets sa
                          WHERE sa.canonical_id = c.canonical_id
                            AND sa.source IN ({placeholders})
                            AND sa.active_in_catalog = 1
                      )
                    """,
                    tuple(successful_sources),
                ).fetchall()
                for row in rows:
                    self.db.deactivate_challenge(conn, row["canonical_id"])
                    if row["availability_start"] and row["availability_start"] >= today:
                        removed_future.append(row["canonical_id"])
                        logger.info("REMOVED_FUTURE %s", row["canonical_id"])
        return removed_future

    def _upsert_source_asset_row(
        self,
        conn: Any,
        source: str,
        challenge: CanonicalChallenge,
        record: dict[str, Any],
    ) -> None:
        self.db.upsert_source_asset(
            conn,
            {
                "source": source,
                "asset_type": self.config.source_config(source).get("assetType", ""),
                "source_identifier": record.get("source_identifier"),
                "canonical_id": challenge.canonical_id,
                "content_type": record.get("content_type") or "Definition",
                "content_version": record.get("content_version"),
                "compatibility_version": record.get("compatibility_version"),
                "sha1": record.get("sha1"),
                "relative_path": record.get("relative_path"),
                "download_url": record.get("download_url"),
                "raw_metadata": json.dumps(challenge.to_dict(), ensure_ascii=False, sort_keys=True),
                "first_seen": challenge.first_seen or utc_now(),
                "last_seen": challenge.last_seen or utc_now(),
                "active_in_catalog": True,
            },
        )

    # ---- canonical diff ----

    def _canonical_diff(
        self,
        merged: dict[str, CanonicalChallenge],
        removed_future: list[str],
        report: UpdateReport,
        existing: dict[str, Any],
    ) -> list[NotificationEvent]:
        """NEW/UPDATED/REMOVED_FUTURE events. ``existing`` is the pre-persist
        snapshot so rows written this round still classify as NEW."""
        events: list[NotificationEvent] = []

        for canonical_id, challenge in merged.items():
            row = existing.get(canonical_id)
            if row is None or not row["active"]:
                report.new_challenges.append(canonical_id)
                logger.info("NEW %s", canonical_id)
                events.append(self._new_event(challenge))
                continue
            if _row_business_fp(row) != challenge.business_fingerprint():
                report.updated_challenges.append(canonical_id)
                logger.info("UPDATED %s", canonical_id)
                events.append(self._updated_event(challenge, row))

        for canonical_id in removed_future:
            report.removed_future.append(canonical_id)
            row = existing.get(canonical_id)
            title = (row["title_zh"] or row["title_en"]) if row else None
            availability = row["availability_start"] if row else None
            sources = json.loads(row["sources"]) if (row and row["sources"]) else []
            events.append(
                NotificationEvent(
                    event_type=REMOVED_FUTURE_CHALLENGE,
                    canonical_id=canonical_id,
                    title=title,
                    availability=availability,
                    sources=sources,
                )
            )
        return events

    def _new_event(self, challenge: CanonicalChallenge) -> NotificationEvent:
        return NotificationEvent(
            event_type=NEW_CHALLENGE,
            canonical_id=challenge.canonical_id,
            title=challenge.title_zh or challenge.title_en,
            scope=_scope_human(challenge),
            availability=challenge.availability_start,
            predicate_human=challenge.predicate_human,
            first_seen=challenge.first_seen,
            sources=challenge.sources,
        )

    def _updated_event(self, challenge: CanonicalChallenge, row: Any) -> NotificationEvent:
        changes: list[str] = []
        if row["predicate_human"] != challenge.predicate_human:
            changes.append(
                f"完成条件：{row['predicate_human'] or '未知'} → {challenge.predicate_human or '未知'}"
            )
        if row["availability_start"] != challenge.availability_start:
            changes.append(
                f"开始日期：{row['availability_start'] or '未知'} → {challenge.availability_start or '未知'}"
            )
        if row["availability_end"] != challenge.availability_end:
            changes.append(
                f"结束日期：{row['availability_end'] or '未知'} → {challenge.availability_end or '未知'}"
            )
        if row["scope_type"] != challenge.scope_type:
            changes.append(f"范围：{row['scope_type']} → {challenge.scope_type}")
        if row["trigger_mask"] != challenge.trigger_mask:
            changes.append(f"触发：{row['trigger_mask']} → {challenge.trigger_mask}")
        if not changes:
            changes.append("规则已更新")
        return NotificationEvent(
            event_type=UPDATED_CHALLENGE,
            canonical_id=challenge.canonical_id,
            title=challenge.title_zh or challenge.title_en,
            scope=_scope_human(challenge),
            availability=challenge.availability_start,
            predicate_human=challenge.predicate_human,
            sources=challenge.sources,
            changes=changes,
            key_salt=challenge.business_fingerprint(),
        )

    # ---- helpers ----

    def _load_active_challenges(self) -> list[CanonicalChallenge]:
        challenges: list[CanonicalChallenge] = []
        for row in self.db.fetch_all_challenges(active_only=True):
            challenge = _row_to_challenge(row)
            if challenge:
                challenges.append(challenge)
        return challenges


def _scope_human(challenge: CanonicalChallenge) -> str:
    if challenge.scope_type == SCOPE_GLOBAL:
        return "全球"
    if challenge.scope_type == "regional":
        return ",".join(challenge.country_codes) + " 限定"
    return "未知"


def _row_business_fp(row: Any) -> str:
    try:
        codes = json.loads(row["country_codes"] or "[]")
    except json.JSONDecodeError:
        codes = []
    return "|".join(
        [
            row["availability_start"] or "",
            row["availability_end"] or "",
            row["visibility_start"] or "",
            row["visibility_end"] or "",
            row["scope_type"] or "",
            ",".join(sorted(codes)),
            row["predicate_raw"] or "",
            str(row["trigger_mask"]) if row["trigger_mask"] is not None else "",
            row["badge_shape"] or "",
        ]
    )


def _challenge_row(challenge: CanonicalChallenge) -> dict[str, Any]:
    return {
        "canonical_id": challenge.canonical_id,
        "title_zh": challenge.title_zh,
        "title_en": challenge.title_en,
        "year": challenge.year,
        "visibility_start": challenge.visibility_start,
        "visibility_end": challenge.visibility_end,
        "availability_start": challenge.availability_start,
        "availability_end": challenge.availability_end,
        "alert_dates": json.dumps(challenge.alert_dates, ensure_ascii=False),
        "scope_type": challenge.scope_type,
        "country_codes": json.dumps(challenge.country_codes),
        "predicate_raw": challenge.predicate_raw,
        "predicate_human": challenge.predicate_human,
        "predicate_parsed": challenge.predicate_parsed,
        "trigger_mask": challenge.trigger_mask,
        "badge_shape": challenge.badge_shape,
        "display_order": challenge.display_order,
        "sources": json.dumps(challenge.sources),
        "first_seen": challenge.first_seen or "",
        "last_seen": challenge.last_seen or "",
        "updated_at": challenge.updated_at or "",
        "sequence": challenge.sequence,
        "active": challenge.active,
    }


def _row_to_challenge(row: Any) -> CanonicalChallenge | None:
    try:
        codes = json.loads(row["country_codes"] or "[]")
        dates = json.loads(row["alert_dates"] or "[]")
        sources = json.loads(row["sources"] or "[]")
    except json.JSONDecodeError:
        return None
    return CanonicalChallenge(
        canonical_id=row["canonical_id"],
        title_zh=row["title_zh"],
        title_en=row["title_en"],
        year=row["year"],
        visibility_start=row["visibility_start"],
        visibility_end=row["visibility_end"],
        availability_start=row["availability_start"],
        availability_end=row["availability_end"],
        alert_dates=dates,
        scope_type=row["scope_type"] or "unknown",
        country_codes=codes,
        predicate_raw=row["predicate_raw"],
        predicate_human=row["predicate_human"],
        predicate_parsed=bool(row["predicate_parsed"]),
        trigger_mask=row["trigger_mask"],
        badge_shape=row["badge_shape"],
        display_order=row["display_order"],
        sources=sources,
        sequence=int(row["sequence"] or 0),
        active=bool(row["active"]),
    )