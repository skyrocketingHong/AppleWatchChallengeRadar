"""Catalog fetching with retry policy and atomic current/previous rotation."""

from __future__ import annotations

import logging
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

USER_AGENT = (
    "AppleWatchChallengeRadar/0.1 "
    "(+https://github.com/skyrocketingHong/AppleWatchChallengeRadar)"
)

# Retry policy: backoff seconds per attempt.
RETRY_BACKOFFS = (5, 30, 120)
DEFAULT_TIMEOUT = 60


@dataclass
class FetchResult:
    ok: bool
    status: str  # FETCH_SUCCESS | FETCH_FAILED
    content: bytes | None = None
    error: str | None = None


class CatalogFetcher:
    """Downloads a MobileAsset catalog XML and keeps current/previous snapshots."""

    def __init__(
        self,
        catalog_dir: Path,
        timeout: float = DEFAULT_TIMEOUT,
        retry_backoffs: tuple[float, ...] = RETRY_BACKOFFS,
    ):
        self.catalog_dir = catalog_dir
        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.retry_backoffs = retry_backoffs

    def fetch(self, url: str) -> FetchResult:
        """Fetch catalog bytes with retries; does not touch disk."""
        last_error: str | None = None
        for attempt, backoff in enumerate((0,) + self.retry_backoffs):
            if attempt > 0:
                logger.warning("catalog retry %d after %.0fs: %s", attempt, backoff, last_error)
                time.sleep(backoff)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    content = resp.read()
                return FetchResult(ok=True, status="FETCH_SUCCESS", content=content)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        return FetchResult(ok=False, status="FETCH_FAILED", error=last_error)

    def save_snapshot(self, content: bytes, rotate: bool = True) -> None:
        """Atomically persist fetched catalog as current.plist, rotating the
        previous content into previous.plist only when the bytes differ."""
        current = self.catalog_dir / "current.plist"
        previous = self.catalog_dir / "previous.plist"

        if rotate and current.exists():
            if current.read_bytes() == content:
                return  # byte-identical; no rotation needed
            tmp_prev = self.catalog_dir / "previous.plist.tmp"
            tmp_prev.write_bytes(content=current.read_bytes())
            tmp_prev.replace(previous)

        tmp = self.catalog_dir / "current.plist.tmp"
        tmp.write_bytes(content)
        tmp.replace(current)

    def archive_snapshot(self, timestamp: str) -> Path | None:
        """Copy current.plist into snapshots/<source>/<timestamp>.plist when the
        Definition set or fingerprints actually changed (caller decides)."""
        current = self.catalog_dir / "current.plist"
        if not current.exists():
            return None
        snapshots = self.catalog_dir.parent / "snapshots" / self.catalog_dir.name
        snapshots.mkdir(parents=True, exist_ok=True)
        dest = snapshots / f"{timestamp}.plist"
        if dest.exists():
            return dest
        shutil.copy2(current, dest)
        return dest

    @staticmethod
    def read_local(catalog_dir: Path) -> bytes | None:
        current = catalog_dir / "current.plist"
        if current.exists():
            return current.read_bytes()
        return None
