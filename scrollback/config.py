"""Runtime settings, read from environment variables.

Nothing secret lives in code. On Cloud Run these come from the service's env and
Secret Manager mounts; locally from your shell.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    project: str
    dataset: str
    archive_bucket: str
    vertex_location: str
    gemini_model: str | None
    backfill_days: int
    drive_folder_id: str | None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            project=_env("SCROLLBACK_PROJECT", required=True),
            dataset=_env("SCROLLBACK_DATASET", "scrollback"),
            archive_bucket=_env("SCROLLBACK_ARCHIVE_BUCKET", required=True),
            vertex_location=_env("SCROLLBACK_VERTEX_LOCATION", "australia-southeast1"),
            # No default on purpose: pick a current Gemini model from the Vertex AI
            # model garden for your location. Model names get retired.
            gemini_model=_env("SCROLLBACK_GEMINI_MODEL"),
            backfill_days=int(_env("SCROLLBACK_BACKFILL_DAYS", "30")),
            drive_folder_id=_env("SCROLLBACK_DRIVE_FOLDER_ID"),
        )
