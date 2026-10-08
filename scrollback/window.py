"""Sync window: from the last watermark, never further back than the backfill limit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def sync_start(
    now: datetime,
    watermark: datetime | None,
    backfill_days: int = 30,
    since: datetime | None = None,
) -> datetime:
    """Earliest save date this sync will process.

    - First sync (no watermark): last `backfill_days`.
    - Later syncs: from the watermark, but capped at `backfill_days` so a
      long gap never pulls in old saves by surprise.
    - `since` (a deliberate one-off) overrides both.
    """
    if since is not None:
        return _utc(since)
    floor = _utc(now) - timedelta(days=backfill_days)
    if watermark is None:
        return floor
    return max(_utc(watermark), floor)


def in_window(saved_at: datetime | None, start: datetime) -> bool:
    """Saves with no date are kept: better to process once than drop silently."""
    if saved_at is None:
        return True
    return _utc(saved_at) >= start


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
