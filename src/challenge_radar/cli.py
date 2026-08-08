"""challenge-radar command line interface.

Commands:
    bootstrap          first-time full import (no historical notifications)
    update             incremental fetch + diff + merge + notify + ICS
    generate           regenerate ICS from SQLite only (no network)
    status             show pipeline health and challenge counts
    inspect-sources    show raw catalog discovery statistics per source
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

from .config import Config, ConfigError
from .runner import STATE_BOOTSTRAP, STATE_LAST_SUCCESS, Pipeline

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=_LOG_FORMAT, stream=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenge-radar",
        description="Apple Watch Limited Edition Challenge Radar",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bootstrap = sub.add_parser("bootstrap", help="first-time full import")
    p_bootstrap.add_argument("--state-dir", type=Path, help="override state dir (dev)")
    p_bootstrap.add_argument("--output-dir", type=Path, help="override ICS output dir (dev)")

    p_update = sub.add_parser("update", help="incremental update")
    p_update.add_argument("--state-dir", type=Path, help="override state dir (dev)")
    p_update.add_argument("--output-dir", type=Path, help="override ICS output dir (dev)")

    sub.add_parser("generate", help="regenerate ICS from SQLite only")
    sub.add_parser("status", help="show status")
    sub.add_parser("inspect-sources", help="show catalog discovery statistics")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    setup_logging(args.verbose)
    try:
        config = Config()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1

    try:
        if args.command in ("bootstrap", "update"):
            return _run_pipeline(args, config)
        if args.command == "generate":
            return _run_generate(config)
        if args.command == "status":
            return _run_status(config)
        if args.command == "inspect-sources":
            return _run_inspect(config)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - top-level guard
        logger.exception("fatal error: %s", exc)
        return 1
    return 0


def _run_pipeline(args: argparse.Namespace, config: Config) -> int:
    state_dir = getattr(args, "state_dir", None)
    output_dir = getattr(args, "output_dir", None)
    pipeline = Pipeline(config, state_dir=state_dir, output_dir=output_dir)
    try:
        if args.command == "bootstrap":
            report = pipeline.bootstrap()
        else:
            report = pipeline.update()
    finally:
        pipeline.close()

    logger.info(
        "report: new=%d updated=%d removed_future=%d notifications=%d ics=%d",
        len(report.new_challenges),
        len(report.updated_challenges),
        len(report.removed_future),
        report.notifications_sent,
        len(report.ics_files),
    )
    return 0


def _run_generate(config: Config) -> int:
    pipeline = Pipeline(config)
    try:
        files = pipeline.generate()
    finally:
        pipeline.close()
    for path in files:
        logger.info("generated %s", path)
    return 0


def _run_status(config: Config) -> int:
    pipeline = Pipeline(config)
    try:
        bootstrap = pipeline.db.get_state(STATE_BOOTSTRAP) == "true"
        last_success = pipeline.db.get_state(STATE_LAST_SUCCESS) or "never"
        last_legacy = pipeline.db.get_state("last_legacy_success") or "never"
        last_current = pipeline.db.get_state("last_current_success") or "never"

        assets_legacy = len(pipeline.db.fetch_source_assets("legacy"))
        assets_current = len(
            [r for r in pipeline.db.fetch_source_assets("current") if r["content_type"] == "Definition"]
        )

        active = pipeline.db.fetch_all_challenges(active_only=True)
        upcoming = pipeline.db.fetch_upcoming_challenges()
        regional = [c for c in active if c["scope_type"] == "regional"]

        last_changed = sorted(
            (r for r in pipeline.db.query("SELECT canonical_id, updated_at FROM challenges")),
            key=lambda r: r["updated_at"] or "",
        )
    finally:
        pipeline.close()

    lines = [
        f"Bootstrap: {'complete' if bootstrap else 'pending'}",
        "",
        "Legacy:",
        f"  last success: {last_legacy}",
        f"  assets: {assets_legacy}",
        f"  status: {'OK' if last_legacy != 'never' else 'UNKNOWN'}",
        "",
        "Current:",
        f"  last success: {last_current}",
        f"  definitions: {assets_current}",
        f"  status: {'OK' if last_current != 'never' else 'UNKNOWN'}",
        "",
        "Challenges:",
        f"  total: {len(active)}",
        f"  upcoming: {len(upcoming)}",
        f"  regional: {len(regional)}",
        "",
        "Last change:",
        f"  {last_changed[-1]['canonical_id'] if last_changed else 'none'}",
        "",
        f"Last successful update: {last_success}",
    ]
    print("\n".join(lines))
    return 0


def _run_inspect(config: Config) -> int:
    from .sources.challenge_assets import ActivityChallengeAssetsAdapter
    from .sources.legacy_achievements import LegacyAchievementsAdapter

    state_dir = config.state_dir
    for name, cls in (("legacy", LegacyAchievementsAdapter), ("current", ActivityChallengeAssetsAdapter)):
        if not config.is_source_enabled(name):
            print(f"\n[{name}] disabled")
            continue
        try:
            adapter = cls(config, state_dir)
            discovery = adapter.discover_schema()
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{name}] discovery failed: {exc}")
            continue
        print(f"\n[{name}] {adapter.asset_type}")
        print(f"  status: {discovery.get('status')}")
        if discovery.get("status") == "ok":
            print(f"  assets: {discovery.get('asset_count')}")
            print(f"  content_types: {discovery.get('content_types')}")
            print(f"  asset_keys: {json.dumps(discovery.get('asset_keys'), ensure_ascii=False)}")
            sample = discovery.get("sample") or []
            for entry in sample[:3]:
                print(f"  sample: {json.dumps(entry, default=str, ensure_ascii=False)[:300]}")
        elif discovery.get("error"):
            print(f"  error: {discovery['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())