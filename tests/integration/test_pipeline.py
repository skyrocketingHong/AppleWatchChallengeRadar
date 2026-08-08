"""End-to-end pipeline tests (design document section 109).

Exercises bootstrap semantics, no-op incremental updates, business-change
detection with sequence bumping, source failure isolation, corrupt definition
recovery, removed-future detection and notification dedup through a real
HTTP webhook. The legacy source is disabled; the Current adapter runs against
the in-memory FakeCurrentAdapter with real ZIP parsing.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from challenge_radar.runner import Pipeline

from ..conftest import FakeCurrentAdapter, make_config
from ..fixtures.definitions import ALL_2026_FIXTURES, make_definition


def _config(webhook_url: str | None = None):
    data = {"sources": {"legacy": {"enabled": False}}}
    if webhook_url:
        data["notifications"] = {
            "enabled": True,
            "providers": {"webhook": {"enabled": True, "url": webhook_url}},
        }
    return make_config(data)


def _pipeline(config, state_dir, output_dir, **adapter_kwargs):
    adapter = FakeCurrentAdapter(
        config, state_dir, definitions=dict(ALL_2026_FIXTURES), **adapter_kwargs
    )
    pipeline = Pipeline(
        config,
        state_dir=state_dir,
        output_dir=output_dir,
        adapters={"current": adapter},
    )
    return pipeline, adapter


class _Collector:
    """Collects JSON bodies POSTed by the webhook provider."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.lock = threading.Lock()

    def handler(self) -> type[BaseHTTPRequestHandler]:
        collector = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                with collector.lock:
                    collector.received.append(json.loads(body))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):  # noqa: ARG002
                pass

        return Handler


# ---- bootstrap semantics ----


def test_bootstrap_imports_all_without_historical_notifications(state_dir, output_dir):
    config = _config()
    pipeline, adapter = _pipeline(config, state_dir, output_dir)
    try:
        report = pipeline.bootstrap()

        assert report.bootstrap is True
        assert report.source_results["current"].ok
        assert len(report.new_challenges) == 7
        assert report.notifications_sent == 0  # bootstrap never sends

        rows = pipeline.db.fetch_all_challenges()
        assert len(rows) == 7
        assert all(r["active"] == 1 for r in rows)

        # Dedup keys recorded even though nothing was sent.
        n = pipeline.db.query("SELECT COUNT(*) AS n FROM notifications")[0]["n"]
        assert n == 7

        # Every feed written.
        names = sorted(p.name for p in output_dir.iterdir())
        assert names == [
            "all.ics",
            "cn.ics",
            "global.ics",
            "history.ics",
            "upcoming.ics",
            "us.ics",
        ]
        assert len(adapter.download_calls) == 7
    finally:
        pipeline.close()


def test_repeat_bootstrap_does_not_duplicate(state_dir, output_dir):
    config = _config()
    pipeline, _ = _pipeline(config, state_dir, output_dir)
    try:
        first = pipeline.bootstrap()
        second = pipeline.bootstrap()

        assert len(first.new_challenges) == 7
        assert second.new_challenges == []
        assert second.notifications_sent == 0
        n = pipeline.db.query("SELECT COUNT(*) AS n FROM notifications")[0]["n"]
        assert n == 7  # no duplicate dedup keys
    finally:
        pipeline.close()


# ---- incremental update ----


def test_second_update_is_noop(state_dir, output_dir):
    config = _config()
    pipeline, adapter = _pipeline(config, state_dir, output_dir)
    try:
        pipeline.bootstrap()
        before = {p.name: p.read_bytes() for p in output_dir.glob("*.ics")}
        calls_after_bootstrap = list(adapter.download_calls)

        report = pipeline.update()

        assert report.new_challenges == []
        assert report.updated_challenges == []
        assert report.removed_future == []
        assert report.notifications_sent == 0
        assert report.ics_files == []  # regenerated only on change

        after = {p.name: p.read_bytes() for p in output_dir.glob("*.ics")}
        assert before == after
        rows = pipeline.db.fetch_all_challenges()
        assert all(r["sequence"] == 0 for r in rows)

        # Live catalog assets never falsely marked as removed.
        assets = pipeline.db.fetch_source_assets("current")
        assert all(r["active_in_catalog"] == 1 for r in assets)
        # No re-downloads on an unchanged catalog.
        assert adapter.download_calls == calls_after_bootstrap
    finally:
        pipeline.close()


def test_predicate_change_detected_as_updated(state_dir, output_dir):
    config = _config()
    pipeline, adapter = _pipeline(config, state_dir, output_dir)
    try:
        pipeline.bootstrap()

        changed = make_definition("CHINA_FITNESS_DAY_2026", predicate="workout.duration >= 2400")
        adapter._definitions["CHINA_FITNESS_DAY_2026"] = changed

        report = pipeline.update()

        assert report.updated_challenges == ["CHINA_FITNESS_DAY_2026"]
        assert report.new_challenges == []
        assert report.removed_future == []
        row = pipeline.db.fetch_challenge("CHINA_FITNESS_DAY_2026")
        assert row["sequence"] == 1
        assert row["predicate_raw"] == "workout.duration >= 2400"
        assert row["active"] == 1

        # ICS regenerated carrying the new predicate.
        content = (output_dir / "cn.ics").read_bytes()
        assert b"workout.duration >= 2400" in content
    finally:
        pipeline.close()


# ---- source failure isolation ----


def test_fetch_failure_preserves_existing_data(state_dir, output_dir):
    config = _config()
    pipeline, adapter = _pipeline(config, state_dir, output_dir)
    try:
        pipeline.bootstrap()
        adapter._fetch_failure = "network down"

        report = pipeline.update()

        assert report.source_results["current"].status == "FETCH_FAILED"
        assert report.new_challenges == []
        assert report.updated_challenges == []
        assert report.removed_future == []
        assert report.ics_files == []

        # Existing challenges untouched and still active.
        rows = pipeline.db.fetch_all_challenges()
        assert len(rows) == 7
        assert all(r["active"] == 1 for r in rows)
    finally:
        pipeline.close()


def test_corrupt_definition_kept_pending_then_recovers(state_dir, output_dir):
    config = _config()
    pipeline, adapter = _pipeline(
        config, state_dir, output_dir, corrupt_zip={"CHINA_FITNESS_DAY_2026"}
    )
    try:
        report = pipeline.bootstrap()

        # The corrupt definition is skipped; the other six imported.
        assert set(report.new_challenges) == set(ALL_2026_FIXTURES) - {"CHINA_FITNESS_DAY_2026"}
        assert len(pipeline.db.fetch_all_challenges()) == 6
        assert pipeline.db.fetch_challenge("CHINA_FITNESS_DAY_2026") is None

        # Bundle fixed; the next update imports the pending challenge.
        adapter._corrupt_zip = set()
        report = pipeline.update()
        assert report.new_challenges == ["CHINA_FITNESS_DAY_2026"]
        assert len(pipeline.db.fetch_all_challenges()) == 7
    finally:
        pipeline.close()


# ---- removed future ----


def test_future_challenge_removed_from_catalog(state_dir, output_dir):
    config = _config()
    definitions = dict(ALL_2026_FIXTURES)
    definitions["FUTURE_TEST_2030"] = make_definition(
        "CHINA_FITNESS_DAY_2026",
        identifier="FUTURE_TEST_2030",
        availabilityStart=datetime(2030, 8, 8, tzinfo=timezone.utc),
        availabilityEnd=datetime(2030, 8, 8, tzinfo=timezone.utc),
    )
    adapter = FakeCurrentAdapter(config, state_dir, definitions=definitions)
    pipeline = Pipeline(
        config,
        state_dir=state_dir,
        output_dir=output_dir,
        adapters={"current": adapter},
    )
    try:
        pipeline.bootstrap()
        assert len(pipeline.db.fetch_all_challenges()) == 8

        # The future challenge vanishes from the next catalog.
        del adapter._definitions["FUTURE_TEST_2030"]
        report = pipeline.update()

        assert report.removed_future == ["FUTURE_TEST_2030"]
        all_rows = pipeline.db.fetch_all_challenges(active_only=False)
        removed = [r for r in all_rows if r["canonical_id"] == "FUTURE_TEST_2030"][0]
        assert removed["active"] == 0
        # Others untouched.
        assert len(pipeline.db.fetch_all_challenges()) == 7
    finally:
        pipeline.close()


# ---- notifications through a real webhook ----


def test_updated_notification_sent_once_via_webhook(state_dir, output_dir):
    collector = _Collector()
    server = HTTPServer(("127.0.0.1", 0), collector.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        config = _config(webhook_url=f"http://127.0.0.1:{port}/hook")
        pipeline, adapter = _pipeline(config, state_dir, output_dir)
        try:
            report = pipeline.bootstrap()
            assert report.notifications_sent == 0

            changed = make_definition("CHINA_FITNESS_DAY_2026", predicate="workout.duration >= 2400")
            adapter._definitions["CHINA_FITNESS_DAY_2026"] = changed

            report = pipeline.update()
            assert report.updated_challenges == ["CHINA_FITNESS_DAY_2026"]
            assert report.notifications_sent == 1

            with collector.lock:
                assert len(collector.received) == 1
                payload = collector.received[0]
            assert payload["event"] == "UPDATED_CHALLENGE"
            assert payload["canonical_id"] == "CHINA_FITNESS_DAY_2026"
            assert payload["changes"]

            # A no-op update sends nothing a second time.
            report = pipeline.update()
            assert report.updated_challenges == []
            assert report.notifications_sent == 0
            with collector.lock:
                assert len(collector.received) == 1
        finally:
            pipeline.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_removed_future_notified_via_webhook(state_dir, output_dir):
    collector = _Collector()
    server = HTTPServer(("127.0.0.1", 0), collector.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        config = _config(webhook_url=f"http://127.0.0.1:{port}/hook")
        definitions = dict(ALL_2026_FIXTURES)
        definitions["FUTURE_TEST_2030"] = make_definition(
            "CHINA_FITNESS_DAY_2026",
            identifier="FUTURE_TEST_2030",
            availabilityStart=datetime(2030, 8, 8, tzinfo=timezone.utc),
            availabilityEnd=datetime(2030, 8, 8, tzinfo=timezone.utc),
        )
        adapter = FakeCurrentAdapter(config, state_dir, definitions=definitions)
        pipeline = Pipeline(
            config,
            state_dir=state_dir,
            output_dir=output_dir,
            adapters={"current": adapter},
        )
        try:
            pipeline.bootstrap()
            del adapter._definitions["FUTURE_TEST_2030"]

            report = pipeline.update()

            assert report.removed_future == ["FUTURE_TEST_2030"]
            assert report.notifications_sent == 1
            with collector.lock:
                assert len(collector.received) == 1
                payload = collector.received[0]
            assert payload["event"] == "REMOVED_FUTURE_CHALLENGE"
            assert payload["canonical_id"] == "FUTURE_TEST_2030"
            assert payload["availability"] == "2030-08-08"  # metadata survives deactivation
        finally:
            pipeline.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)