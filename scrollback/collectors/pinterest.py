"""Pinterest pins, via the Pinterest API v5 (read-only scopes).

Needs an access token for your own account: boards:read, pins:read,
user_accounts:read (plus the _secret variants for secret boards).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx

from scrollback.archive import Archive, archive_url
from scrollback.collectors import recipe_page
from scrollback.models import RawSave, Source
from scrollback.window import in_window

API = "https://api.pinterest.com/v5"


class PinterestClient:
    def __init__(self, access_token: str, http: httpx.Client):
        self._http = http
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def _pages(self, path: str, params: dict | None = None) -> Iterator[dict]:
        params = {"page_size": 100, **(params or {})}
        while True:
            resp = self._http.get(f"{API}{path}", params=params, headers=self._headers, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            yield from body.get("items", [])
            bookmark = body.get("bookmark")
            if not bookmark:
                return
            params["bookmark"] = bookmark

    def boards(self) -> Iterator[dict]:
        return self._pages("/boards")

    def board_pins(self, board_id: str) -> Iterator[dict]:
        return self._pages(f"/boards/{board_id}/pins")


def collect(
    client: PinterestClient,
    start: datetime,
    archive: Archive,
    http: httpx.Client,
    captured_at: datetime | None = None,
    capture_links: bool = True,
) -> Iterator[RawSave]:
    captured_at = captured_at or datetime.now(UTC)
    for board in client.boards():
        for pin in client.board_pins(board["id"]):
            saved_at = _parse(pin.get("created_at"))
            if not in_window(saved_at, start):
                continue
            yield to_raw_save(pin, board.get("name"), saved_at, captured_at, archive, http,
                              capture_links)


def to_raw_save(pin, board_name, saved_at, captured_at, archive, http, capture_links=True):
    pin_id = pin["id"]
    files = []
    for i, url in enumerate(image_urls(pin)):
        f = archive_url(archive, http, Source.PINTEREST, pin_id, f"image{i}", url)
        if f:
            files.append(f)
    link = pin.get("link")
    linked = recipe_page.capture(http, link) if (capture_links and link) else None
    return RawSave(
        source=Source.PINTEREST,
        source_id=pin_id,
        url=f"https://www.pinterest.com/pin/{pin_id}/",
        saved_at=saved_at,
        captured_at=captured_at,
        title=pin.get("title") or None,
        caption=pin.get("description") or None,
        board=board_name,
        outbound_link=link,
        linked_page=linked,
        files=files,
        source_payload=pin,
    )


def image_urls(pin: dict) -> list[str]:
    """Largest image per media item; carousels give several."""
    media = pin.get("media") or {}
    groups = []
    if media.get("images"):
        groups.append(media["images"])
    for item in media.get("items") or []:
        if item.get("images"):
            groups.append(item["images"])
    urls = []
    for images in groups:
        best = max(
            (v for v in images.values() if isinstance(v, dict) and v.get("url")),
            key=lambda v: (v.get("width") or 0) * (v.get("height") or 0),
            default=None,
        )
        if best:
            urls.append(best["url"])
    return urls


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
