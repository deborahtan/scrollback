from datetime import UTC, datetime, timedelta

from scrollback.window import in_window, sync_start

NOW = datetime(2026, 10, 9, tzinfo=UTC)


def test_first_sync_backfills_30_days():
    assert sync_start(NOW, None) == NOW - timedelta(days=30)


def test_later_sync_starts_at_watermark():
    wm = NOW - timedelta(days=3)
    assert sync_start(NOW, wm) == wm


def test_long_gap_is_capped_at_backfill_limit():
    wm = NOW - timedelta(days=90)
    assert sync_start(NOW, wm) == NOW - timedelta(days=30)


def test_since_overrides_for_one_off_backfill():
    since = datetime(2026, 1, 1, tzinfo=UTC)
    assert sync_start(NOW, NOW, since=since) == since


def test_naive_datetimes_treated_as_utc():
    assert sync_start(datetime(2026, 10, 9), None) == NOW - timedelta(days=30)


def test_undated_saves_are_kept():
    assert in_window(None, NOW)
    assert not in_window(NOW - timedelta(days=1), NOW)
