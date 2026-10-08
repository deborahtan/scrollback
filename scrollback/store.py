"""BigQuery persistence. Snapshots are append-only; cards are upserted."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from google.cloud import bigquery

from scrollback.models import ItemCard, RawSave


class Store:
    def __init__(self, project: str, dataset: str, client: bigquery.Client | None = None):
        self.bq = client or bigquery.Client(project=project)
        self.ds = f"{project}.{dataset}"

    def watermark(self, source: str) -> datetime | None:
        rows = self.bq.query(
            f"SELECT MAX(started_at) AS w FROM `{self.ds}.sync_runs` "
            "WHERE source = @s AND status IN ('ok', 'partial')",
            job_config=_params(s=source),
        ).result()
        return next(iter(rows)).w

    def known_hashes(self, item_keys: list[str]) -> set[tuple[str, str]]:
        if not item_keys:
            return set()
        rows = self.bq.query(
            f"SELECT item_key, content_hash FROM `{self.ds}.raw_saves` "
            "WHERE item_key IN UNNEST(@k)",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ArrayQueryParameter("k", "STRING", item_keys)]
            ),
        ).result()
        return {(r.item_key, r.content_hash) for r in rows}

    def add_snapshots(self, saves: list[RawSave], sync_run_id: str) -> None:
        rows = [
            {
                "item_key": s.item_key,
                "source": s.source.value,
                "source_id": s.source_id,
                "content_hash": s.content_hash(),
                "url": s.url,
                "saved_at": s.saved_at.isoformat() if s.saved_at else None,
                "captured_at": s.captured_at.isoformat(),
                "snapshot": s.model_dump_json(),
                "sync_run_id": sync_run_id,
            }
            for s in saves
        ]
        _insert(self.bq, f"{self.ds}.raw_saves", rows)

    def upsert_card(self, save: RawSave, card: ItemCard, model: str, prompt_version: str) -> None:
        thumb = next((f.gcs_uri for f in save.files if f.kind in ("thumbnail", "image0")), None)
        row = {
            "item_key": save.item_key,
            "source": save.source.value,
            "url": save.url,
            "saved_at": save.saved_at.isoformat() if save.saved_at else None,
            "content_hash": save.content_hash(),
            **card.model_dump(mode="json"),
            "thumbnail_uri": thumb,
            "source_status": "live",
            "extractor_model": model,
            "prompt_version": prompt_version,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        cols = list(row)
        updates = ", ".join(f"{c} = S.{c}" for c in cols if c != "item_key")
        inserts = ", ".join(cols)
        values = ", ".join(f"S.{c}" for c in cols)
        self.bq.query(
            f"""
            MERGE `{self.ds}.items` T
            USING (SELECT * FROM UNNEST([STRUCT<{_struct_types(row)}>({_placeholders(cols)})])) S
            ON T.item_key = S.item_key
            WHEN MATCHED THEN UPDATE SET {updates}
            WHEN NOT MATCHED THEN INSERT ({inserts}) VALUES ({values})
            """,
            job_config=_row_params(row),
        ).result()

    def record_run(self, run: dict) -> None:
        run = {**run, "failures": json.dumps(run.get("failures") or [])}
        _insert(self.bq, f"{self.ds}.sync_runs", [run])


def _insert(client: bigquery.Client, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    errors = client.insert_rows_json(table, rows)
    if errors:
        raise RuntimeError(f"BigQuery insert into {table} failed: {errors[:3]}")


def _params(**kw) -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter(k, "STRING", v) for k, v in kw.items()]
    )


_TYPES = {
    "saved_at": "TIMESTAMP", "updated_at": "TIMESTAMP", "minutes": "INT64",
    "has_full_method": "BOOL", "key_elements": "ARRAY<STRING>", "vibe_tags": "ARRAY<STRING>",
}


def _struct_types(row: dict) -> str:
    return ", ".join(f"{c} {_TYPES.get(c, 'STRING')}" for c in row)


def _placeholders(cols: list[str]) -> str:
    return ", ".join(f"@{c}" for c in cols)


def _row_params(row: dict) -> bigquery.QueryJobConfig:
    params = []
    for c, v in row.items():
        t = _TYPES.get(c, "STRING")
        if t.startswith("ARRAY"):
            params.append(bigquery.ArrayQueryParameter(c, "STRING", v or []))
        else:
            params.append(bigquery.ScalarQueryParameter(c, t, v))
    return bigquery.QueryJobConfig(query_parameters=params)
