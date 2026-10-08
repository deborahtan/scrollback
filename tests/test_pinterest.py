from datetime import UTC, datetime

import httpx

from scrollback.archive import LocalArchive
from scrollback.collectors import pinterest

PIN = {
    "id": "111",
    "created_at": "2026-10-02T10:00:00",
    "title": "90s layered look",
    "description": "knee-high boots, leather jacket",
    "link": None,
    "media": {"media_type": "image", "images": {
        "150x150": {"url": "https://i.example/s.jpg", "width": 150, "height": 150},
        "1200x": {"url": "https://i.example/l.jpg", "width": 1200, "height": 1600},
    }},
}
OLD_PIN = {**PIN, "id": "222", "created_at": "2026-01-01T10:00:00"}


def _http():
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.path == "/v5/boards":
            return httpx.Response(200, json={"items": [{"id": "b1", "name": "Outfits"}],
                                             "bookmark": None})
        if r.url.path == "/v5/boards/b1/pins":
            if "bookmark" not in r.url.params:
                return httpx.Response(200, json={"items": [PIN], "bookmark": "next"})
            return httpx.Response(200, json={"items": [OLD_PIN], "bookmark": None})
        if r.url.host == "i.example":
            return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_largest_image_chosen():
    assert pinterest.image_urls(PIN) == ["https://i.example/l.jpg"]


def test_collect_pages_and_filters_window(tmp_path):
    http = _http()
    client = pinterest.PinterestClient("token", http)
    start = datetime(2026, 9, 9, tzinfo=UTC)
    saves = list(pinterest.collect(client, start, LocalArchive(tmp_path), http))
    assert [s.source_id for s in saves] == ["111"]
    assert saves[0].board == "Outfits"
    assert saves[0].files[0].kind == "image0"
