# Scrollback

Nothing to wear? Don't know what to make? You have hundreds of ideas saved across
Pinterest and TikTok. Scrollback turns them into three you can act on today.

Full design: [Scrollback architecture doc](https://claude.ai/code/artifact/cb01f59f-52ad-49fb-afb3-ca8ecf6ea70a)
(summary in [docs/architecture.md](docs/architecture.md)).

## Status: phase 1 (catalogue)

| Piece | State |
| --- | --- |
| TikTok export collector (30-day window, oEmbed snapshot, thumbnail archive) | done |
| Pinterest collector (API v5, all boards, largest images, linked recipe capture) | done |
| Drive collector (folder shared with service account, full file copy) | done |
| Snapshot at ingest (content-hashed, immutable, survives deleted posts) | done |
| Extractor (typed item cards, injection-safe, ingredient grounding check) | done |
| BigQuery store (raw_saves, items, sync_runs) and sync receipt | done |
| GCP bootstrap script (APIs, bucket, dataset, service accounts, keyless GitHub deploys) | done |
| Deploy workflow (Cloud Run job + monthly scheduler) | next |
| Phase 2: Retriever, Curator, Critic, prompt-to-filters app | after |

## Setup

1. **Google Cloud:** open [Cloud Shell](https://shell.cloud.google.com) (works on a phone), then:
   ```bash
   git clone https://github.com/deborahtan/scrollback && cd scrollback
   bash infra/bootstrap.sh YOUR_PROJECT_ID
   ```
   It prints the service-account email to share your Drive folder with, and the
   GitHub variables to add.
2. **Pinterest:** business account, then create an app at developers.pinterest.com and
   request Trial access. Read scopes only.
3. **TikTok:** Settings and privacy, Account, Download your data, JSON, include Activity.

## Run a sync

```bash
export SCROLLBACK_PROJECT=... SCROLLBACK_ARCHIVE_BUCKET=... SCROLLBACK_GEMINI_MODEL=...
scrollback-sync --source pinterest
scrollback-sync --source drive
scrollback-sync --source tiktok --tiktok-export user_data_tiktok.json
scrollback-sync --source pinterest --since 2026-06-01   # one-off older backfill
```

`SCROLLBACK_GEMINI_MODEL` has no default on purpose: pick a current Gemini model
available in your Vertex AI location.

## Design rules this code follows

- **Snapshot at ingest.** Every save is copied (text, images, linked recipe) the moment it
  syncs and never overwritten. Deleted posts stay in your library.
- **Backfill is one month.** Older saves only come in with an explicit `--since`.
- **Captions are untrusted.** The Extractor has no tools, sees content as quoted data, must
  return schema-valid JSON, and any ingredient not in the source is dropped.
- **No keys in the repo.** GitHub deploys through Workload Identity Federation; Pinterest
  tokens live in Secret Manager. Preferences live in the versioned archive bucket.

## Develop

```bash
pip install -e ".[dev]"
pytest -q && ruff check .
```
