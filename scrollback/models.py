"""Typed records that flow through the pipeline.

RawSave   - what a collector captured at sync time (the snapshot).
ItemCard  - what the Extractor writes from a snapshot (the catalogue card).

Every LLM output must validate against ItemCard before it is stored.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class Source(StrEnum):
    TIKTOK = "tiktok"
    PINTEREST = "pinterest"
    DRIVE = "drive"


class Category(StrEnum):
    RECIPE = "recipe"
    OUTFIT = "outfit"
    MAKE = "make"  # craft or art project
    PLACE = "place"  # somewhere to go or something to do
    OTHER = "other"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ArchivedFile(BaseModel):
    """A file copied into the archive bucket at sync time."""

    kind: str  # "thumbnail", "image", "document"
    gcs_uri: str
    content_type: str | None = None
    sha256: str | None = None


class LinkedPage(BaseModel):
    """Recipe or article data captured from a link inside a pin."""

    url: str
    title: str | None = None
    recipe: dict | None = None  # schema.org Recipe JSON-LD, as published
    text_excerpt: str | None = None  # fallback when no structured data exists


class RawSave(BaseModel):
    """Immutable snapshot of one save, taken when it synced."""

    source: Source
    source_id: str
    url: str
    saved_at: datetime | None = None
    captured_at: datetime
    title: str | None = None
    caption: str | None = None
    creator: str | None = None
    board: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    outbound_link: str | None = None
    extracted_text: str | None = None
    linked_page: LinkedPage | None = None
    files: list[ArchivedFile] = Field(default_factory=list)
    source_payload: dict = Field(default_factory=dict)

    @property
    def item_key(self) -> str:
        """Stable ID for the save across syncs."""
        return f"{self.source.value}:{self.source_id}"

    def content_hash(self) -> str:
        """Hash of the user-visible content. A changed caption gives a new hash,
        so both versions are kept rather than overwritten."""
        visible = {
            "title": self.title,
            "caption": self.caption,
            "outbound_link": self.outbound_link,
            "extracted_text": self.extracted_text,
            "linked_page": self.linked_page.model_dump() if self.linked_page else None,
            "files": sorted(f.sha256 or f.gcs_uri for f in self.files),
        }
        blob = json.dumps(visible, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()


class ItemCard(BaseModel):
    """Catalogue card the Extractor writes for each save."""

    category: Category
    title: str = Field(max_length=120)
    key_elements: list[str] = Field(
        default_factory=list,
        description="Ingredients, clothing pieces or materials, as named in the source",
        max_length=40,
    )
    vibe_tags: list[str] = Field(default_factory=list, max_length=12)
    effort: Effort | None = None
    minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    cuisine: str | None = None
    season: str | None = None
    summary: str | None = Field(default=None, max_length=400)
    has_full_method: bool = Field(
        default=False,
        description="True only if the snapshot contains the full steps, not just a teaser",
    )

    @field_validator("key_elements", "vibe_tags")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for v in values:
            v = v.strip().lower()
            if v:
                seen.setdefault(v, None)
        return list(seen)
