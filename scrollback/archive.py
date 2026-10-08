"""Copies images and files into the archive bucket at sync time.

Snapshots are content-addressed (sha256 in the path), so the same image is stored
once and a changed image is stored alongside the old one, never over it.
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Protocol

import httpx

from scrollback.models import ArchivedFile, Source

MAX_BYTES = 25 * 1024 * 1024  # skip anything larger than 25 MB


class Archive(Protocol):
    def put(self, key: str, data: bytes, content_type: str | None) -> str: ...


class GcsArchive:
    def __init__(self, bucket: str, client=None):
        from google.cloud import storage

        self._bucket = (client or storage.Client()).bucket(bucket)
        self._name = bucket

    def put(self, key: str, data: bytes, content_type: str | None) -> str:
        blob = self._bucket.blob(key)
        if not blob.exists():
            blob.upload_from_string(data, content_type=content_type)
        return f"gs://{self._name}/{key}"


class LocalArchive:
    """For tests and local dry runs."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, key: str, data: bytes, content_type: str | None) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return path.as_uri()


def archive_bytes(
    archive: Archive,
    source: Source,
    source_id: str,
    kind: str,
    data: bytes,
    content_type: str | None,
) -> ArchivedFile:
    digest = hashlib.sha256(data).hexdigest()
    ext = (mimetypes.guess_extension(content_type or "") or "").lstrip(".") or "bin"
    key = f"{source.value}/{source_id}/{kind}-{digest[:16]}.{ext}"
    uri = archive.put(key, data, content_type)
    return ArchivedFile(kind=kind, gcs_uri=uri, content_type=content_type, sha256=digest)


def archive_url(
    archive: Archive,
    http: httpx.Client,
    source: Source,
    source_id: str,
    kind: str,
    url: str,
) -> ArchivedFile | None:
    """Download a public image URL and archive it. Returns None on failure:
    a missing thumbnail must never fail the whole sync."""
    try:
        resp = http.get(url, follow_redirects=True, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    if len(resp.content) > MAX_BYTES:
        return None
    content_type = resp.headers.get("content-type", "").split(";")[0] or None
    return archive_bytes(archive, source, source_id, kind, resp.content, content_type)
