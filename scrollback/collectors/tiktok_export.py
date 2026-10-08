"""TikTok favourites, from the official "Download your data" JSON export.

TikTok has no API for your favourites, so the export is the source. It contains
the link and favourite date for each video; caption, creator and thumbnail are
added from TikTok's public oEmbed endpoint at sync time and snapshotted.

The export's key names have changed over time ("Activity" vs "Your Activity",
"Date" vs "date"), so lookups are case- and path-tolerant.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx

from scrollback.archive import Archive, archive_url
from scrollback.models import RawSave, Source
from scrollback.window import in_window

OEMBED = "https://www.tiktok.com/oembed"
_VIDEO_ID = re.compile(r"/(?:video|v)/(\d+)")
_HASHTAG = re.compile(r"#(\w+)")


def load_favourites(path: Path) -> list[dict]:
    """Return [{"link": str, "date": datetime | None}] from an export file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = _find_list(data, "favoritevideolist")
    if entries is None:
        raise ValueError(
            "No favourite videos found. Re-request the export in JSON with Activity included."
        )
    out = []
    for entry in entries:
        lowered = {k.lower(): v for k, v in entry.items()}
        link = lowered.get("link") or lowered.get("videolink") or lowered.get("url")
        if not link:
            continue
        out.append({"link": link.strip(), "date": _parse_date(lowered.get("date"))})
    return out


def video_id(link: str) -> str | None:
    match = _VIDEO_ID.search(link)
    return match.group(1) if match else None


def collect(
    export_path: Path,
    start: datetime,
    archive: Archive,
    http: httpx.Client,
    captured_at: datetime | None = None,
) -> Iterator[RawSave]:
    captured_at = captured_at or datetime.now(UTC)
    for fav in load_favourites(export_path):
        if not in_window(fav["date"], start):
            continue
        vid = video_id(fav["link"]) or fav["link"]
        meta = _oembed(http, fav["link"])
        caption = meta.get("title")
        files = []
        if meta.get("thumbnail_url"):
            thumb = archive_url(
                archive, http, Source.TIKTOK, vid, "thumbnail", meta["thumbnail_url"]
            )
            if thumb:
                files.append(thumb)
        yield RawSave(
            source=Source.TIKTOK,
            source_id=vid,
            url=fav["link"],
            saved_at=fav["date"],
            captured_at=captured_at,
            caption=caption,
            creator=meta.get("author_unique_id") or meta.get("author_name"),
            hashtags=_HASHTAG.findall(caption or ""),
            files=files,
            source_payload={"export": {"link": fav["link"]}, "oembed": meta},
        )


def _oembed(http: httpx.Client, link: str) -> dict:
    """Public metadata for a video. Empty dict if the video is gone or blocked;
    the save is still recorded with its link and date."""
    try:
        resp = http.get(OEMBED, params={"url": link}, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return {}
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return {}
    keep = ("title", "author_name", "author_unique_id", "author_url", "thumbnail_url")
    return {k: data[k] for k in keep if data.get(k)}


def _find_list(node, key: str):
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower().replace(" ", "") == key and isinstance(v, list):
                return v
        for v in node.values():
            found = _find_list(v, key)
            if found is not None:
                return found
    return None


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
