import json
from datetime import UTC, datetime

import httpx

from scrollback.archive import LocalArchive
from scrollback.collectors import tiktok_export


def _export(tmp_path, wrapper="Activity", date_key="Date", link_key="Link"):
    data = {
        wrapper: {
            "Favorite Videos": {
                "FavoriteVideoList": [
                    {date_key: "2026-10-01 08:00:00",
                     link_key: "https://www.tiktokv.com/share/video/7400000000000000001/"},
                    {date_key: "2026-06-01 08:00:00",
                     link_key: "https://www.tiktokv.com/share/video/7400000000000000002/"},
                ]
            }
        }
    }
    path = tmp_path / "user_data_tiktok.json"
    path.write_text(json.dumps(data))
    return path


def test_loads_old_and_new_export_shapes(tmp_path):
    for wrapper, dk, lk in [("Activity", "Date", "Link"), ("Your Activity", "date", "link")]:
        favs = tiktok_export.load_favourites(_export(tmp_path, wrapper, dk, lk))
        assert len(favs) == 2
        assert favs[0]["date"] == datetime(2026, 10, 1, 8, tzinfo=UTC)


def test_video_id():
    assert tiktok_export.video_id("https://www.tiktok.com/@a/video/123456") == "123456"


def _http():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oembed":
            return httpx.Response(200, json={
                "title": "Easy miso ramen #ramen #dinner",
                "author_unique_id": "cookwithme",
                "thumbnail_url": "https://img.example/thumb.jpg",
            })
        if request.url.host == "img.example":
            return httpx.Response(200, content=b"jpegbytes", headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_collect_snapshots_only_inside_window(tmp_path):
    archive = LocalArchive(tmp_path / "archive")
    start = datetime(2026, 9, 9, tzinfo=UTC)
    saves = list(tiktok_export.collect(_export(tmp_path), start, archive, _http()))
    assert len(saves) == 1
    s = saves[0]
    assert s.source_id == "7400000000000000001"
    assert s.caption.startswith("Easy miso ramen")
    assert s.hashtags == ["ramen", "dinner"]
    assert s.creator == "cookwithme"
    assert s.files and s.files[0].kind == "thumbnail"
    assert (tmp_path / "archive").rglob("*.jpg")


def test_deleted_video_still_recorded(tmp_path):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    start = datetime(2026, 9, 9, tzinfo=UTC)
    saves = list(tiktok_export.collect(_export(tmp_path), start, LocalArchive(tmp_path), http))
    assert len(saves) == 1 and saves[0].caption is None and saves[0].files == []
