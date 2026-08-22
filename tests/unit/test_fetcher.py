from challenge_radar.catalog.fetcher import CatalogFetcher


def test_save_snapshot_rotates_changed_content(tmp_path):
    fetcher = CatalogFetcher(tmp_path)

    fetcher.save_snapshot(b"old catalog")
    fetcher.save_snapshot(b"new catalog")

    assert (tmp_path / "current.plist").read_bytes() == b"new catalog"
    assert (tmp_path / "previous.plist").read_bytes() == b"old catalog"
