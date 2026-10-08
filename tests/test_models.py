from datetime import UTC, datetime

from scrollback.models import RawSave, Source


def _save(caption):
    return RawSave(source=Source.PINTEREST, source_id="9", url="u",
                   captured_at=datetime(2026, 10, 9, tzinfo=UTC), caption=caption)


def test_item_key_is_stable():
    assert _save("a").item_key == "pinterest:9"


def test_edited_caption_gives_new_hash_so_both_versions_are_kept():
    assert _save("a").content_hash() != _save("b").content_hash()


def test_capture_time_does_not_change_hash():
    a = _save("a")
    b = a.model_copy(update={"captured_at": datetime(2027, 1, 1, tzinfo=UTC)})
    assert a.content_hash() == b.content_hash()
