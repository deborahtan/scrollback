-- Scrollback phase 1 tables. Apply with: scripts/apply_schema.sh <project> <dataset>
-- `${dataset}` is substituted by the script.

-- Immutable snapshots: one row per (item_key, content_hash). Never updated.
CREATE TABLE IF NOT EXISTS `${dataset}.raw_saves` (
  item_key        STRING NOT NULL,
  source          STRING NOT NULL,
  source_id       STRING NOT NULL,
  content_hash    STRING NOT NULL,
  url             STRING,
  saved_at        TIMESTAMP,
  captured_at     TIMESTAMP NOT NULL,
  snapshot        JSON NOT NULL,      -- full RawSave, including archived file URIs
  sync_run_id     STRING
)
PARTITION BY DATE(captured_at)
CLUSTER BY source, item_key;

-- One catalogue card per save, built from its latest snapshot.
CREATE TABLE IF NOT EXISTS `${dataset}.items` (
  item_key        STRING NOT NULL,
  source          STRING NOT NULL,
  url             STRING,
  saved_at        TIMESTAMP,
  content_hash    STRING NOT NULL,    -- snapshot this card was built from
  category        STRING,
  title           STRING,
  key_elements    ARRAY<STRING>,
  vibe_tags       ARRAY<STRING>,
  effort          STRING,
  minutes         INT64,
  cuisine         STRING,
  season          STRING,
  summary         STRING,
  has_full_method BOOL,
  thumbnail_uri   STRING,
  source_status   STRING,             -- live | source_gone
  extractor_model STRING,
  prompt_version  STRING,
  updated_at      TIMESTAMP NOT NULL
)
CLUSTER BY category, source;

-- One row per sync, per source. The latest ok row is the watermark.
CREATE TABLE IF NOT EXISTS `${dataset}.sync_runs` (
  sync_run_id     STRING NOT NULL,
  source          STRING NOT NULL,
  trigger         STRING,             -- push | share | monthly | backfill
  window_start    TIMESTAMP,
  started_at      TIMESTAMP NOT NULL,
  finished_at     TIMESTAMP,
  status          STRING,             -- ok | partial | failed
  seen            INT64,
  new_snapshots   INT64,
  cards_written   INT64,
  failures        JSON
);
