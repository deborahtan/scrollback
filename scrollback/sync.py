"""Sync runner: collect -> snapshot -> extract -> store -> receipt.

Examples:
  scrollback-sync --source pinterest
  scrollback-sync --source drive
  scrollback-sync --source tiktok --tiktok-export user_data_tiktok.json
  scrollback-sync --source pinterest --since 2026-06-01   # one-off older backfill
"""

from __future__ import annotations

import argparse
import os
import uuid
from datetime import UTC, datetime

import httpx

from scrollback.archive import GcsArchive
from scrollback.collectors import drive, pinterest, tiktok_export
from scrollback.config import Settings
from scrollback.extractor import PROMPT_VERSION, extract, gemini_generator
from scrollback.models import RawSave
from scrollback.store import Store
from scrollback.window import sync_start


def run(source: str, trigger: str = "push", since: datetime | None = None,
        tiktok_export_path: str | None = None) -> dict:
    s = Settings.from_env()
    if not s.gemini_model:
        raise RuntimeError("Set SCROLLBACK_GEMINI_MODEL to a current Gemini model name.")
    store = Store(s.project, s.dataset)
    archive = GcsArchive(s.archive_bucket)
    now = datetime.now(UTC)
    start = sync_start(now, store.watermark(source), s.backfill_days, since)
    run_id = str(uuid.uuid4())
    failures: list[dict] = []

    with httpx.Client() as http:
        saves = list(_collect(source, start, archive, http, s, tiktok_export_path))

    known = store.known_hashes([sv.item_key for sv in saves])
    new = [sv for sv in saves if (sv.item_key, sv.content_hash()) not in known]
    store.add_snapshots(new, run_id)

    generate = gemini_generator(s.project, s.vertex_location, s.gemini_model)
    cards = 0
    for save in new:
        result = extract(save, generate)
        if result.card is None:
            failures.append({"item_key": save.item_key, "error": result.error})
            continue
        store.upsert_card(save, result.card, s.gemini_model, PROMPT_VERSION)
        cards += 1

    receipt = {
        "sync_run_id": run_id,
        "source": source,
        "trigger": trigger,
        "window_start": start.isoformat(),
        "started_at": now.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "status": "ok" if not failures else ("partial" if cards else "failed"),
        "seen": len(saves),
        "new_snapshots": len(new),
        "cards_written": cards,
        "failures": failures,
    }
    store.record_run(receipt)
    return receipt


def _collect(source, start, archive, http, s: Settings, tiktok_export_path) -> list[RawSave]:
    if source == "tiktok":
        if not tiktok_export_path:
            raise SystemExit("--tiktok-export is required for TikTok")
        return tiktok_export.collect(tiktok_export_path, start, archive, http)
    if source == "pinterest":
        token = os.environ.get("PINTEREST_ACCESS_TOKEN")
        if not token:
            raise SystemExit("PINTEREST_ACCESS_TOKEN is not set")
        return pinterest.collect(pinterest.PinterestClient(token, http), start, archive, http)
    if source == "drive":
        if not s.drive_folder_id:
            raise SystemExit("SCROLLBACK_DRIVE_FOLDER_ID is not set")
        return drive.collect(drive.drive_service(), s.drive_folder_id, start, archive)
    raise SystemExit(f"Unknown source: {source}")


def receipt_line(r: dict) -> str:
    failed = len(r["failures"])
    line = f"{r['source'].title()}: {r['cards_written']} new saves added"
    return line + (f", {failed} couldn't be read" if failed else "") + "."


def main() -> None:
    p = argparse.ArgumentParser(description="Sync saves into Scrollback")
    p.add_argument("--source", required=True, choices=["tiktok", "pinterest", "drive"])
    p.add_argument("--trigger", default="push", choices=["push", "share", "monthly", "backfill"])
    p.add_argument("--since", type=datetime.fromisoformat, default=None)
    p.add_argument("--tiktok-export", default=None)
    args = p.parse_args()
    print(receipt_line(run(args.source, args.trigger, args.since, args.tiktok_export)))


if __name__ == "__main__":
    main()
