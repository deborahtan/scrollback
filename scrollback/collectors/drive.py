"""Drive files in your Scrollback inspo folder.

The runtime service account reads the folder because you share it with that
account as Viewer, so no Drive OAuth is needed. Each file is copied in full into
the archive (it's yours), and Google Docs are also exported as plain text.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import UTC, datetime

from scrollback.archive import Archive, archive_bytes
from scrollback.models import RawSave, Source
from scrollback.window import in_window

GOOGLE_DOC = "application/vnd.google-apps.document"
MAX_BYTES = 25 * 1024 * 1024


def drive_service():
    import google.auth
    from googleapiclient.discovery import build

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_files(service, folder_id: str, start: datetime) -> Iterator[dict]:
    query = (
        f"'{folder_id}' in parents and trashed = false "
        f"and modifiedTime >= '{start.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S')}'"
    )
    page_token = None
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink)",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        yield from resp.get("files", [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            return


def collect(
    service,
    folder_id: str,
    start: datetime,
    archive: Archive,
    captured_at: datetime | None = None,
) -> Iterator[RawSave]:
    captured_at = captured_at or datetime.now(UTC)
    for f in list_files(service, folder_id, start):
        modified = datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00"))
        if not in_window(modified, start):
            continue
        files, text = [], None
        if f["mimeType"] == GOOGLE_DOC:
            text = service.files().export(fileId=f["id"], mimeType="text/plain").execute()
            text = text.decode("utf-8", "replace") if isinstance(text, bytes) else text
            pdf = service.files().export(fileId=f["id"], mimeType="application/pdf").execute()
            files.append(archive_bytes(archive, Source.DRIVE, f["id"], "document", pdf,
                                       "application/pdf"))
        elif f["mimeType"].startswith("application/vnd.google-apps"):
            continue  # Sheets, Slides etc. are out of scope for now
        elif int(f.get("size") or 0) <= MAX_BYTES:
            data = _download(service, f["id"])
            files.append(archive_bytes(archive, Source.DRIVE, f["id"], "document", data,
                                       f["mimeType"]))
        yield RawSave(
            source=Source.DRIVE,
            source_id=f["id"],
            url=f.get("webViewLink") or f"https://drive.google.com/file/d/{f['id']}",
            saved_at=modified,
            captured_at=captured_at,
            title=f["name"],
            extracted_text=text,
            files=files,
            source_payload=f,
        )


def _download(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    buf = io.BytesIO()
    request = service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()
