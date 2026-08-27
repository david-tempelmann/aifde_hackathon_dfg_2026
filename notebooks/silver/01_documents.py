# Databricks notebook source
# MAGIC %md
# MAGIC # Silver 01 — documents
# MAGIC Normalize the raw layer (`raw_issues`) into a clean, citable document table.
# MAGIC
# MAGIC - 1:1 with `raw_issues` (one document per scraped item).
# MAGIC - `full_text` = title + cleaned content, the exact text we chunk and cite against.
# MAGIC - `content_hash` on the normalized main text — a stable change-detection key for a
# MAGIC   later incremental path (see solution-design §6); unused while we full-reprocess.
# MAGIC
# MAGIC Full reprocess: `CREATE OR REPLACE` rebuilds from scratch each run.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
print(f"Building {catalog}.{schema}.documents")

# COMMAND ----------

# Notes on normalization:
# - Content is already mostly clean text (only a handful of rows carry HTML), so
#   we do a light pass: strip any tags, unescape a few common entities, collapse
#   whitespace. Deliberately not a full HTML-readability step — that belongs in
#   ingest (WP1), not here.
# - `full_text` concatenates title and body so a signal grounded in either is
#   locatable by one set of character offsets.
# - Date strings vary by source ("Aug 25, 2026", ISO, m/d/Y); we try a few
#   formats and fall back to the first-seen timestamp so `published_date` is
#   never null.
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.documents AS
WITH cleaned AS (
  SELECT
    issue_id                                   AS document_id,
    source,
    source_type,
    region,
    bias,
    title,
    url,
    content                                    AS raw_content,
    -- light main-text normalization
    trim(regexp_replace(
      regexp_replace(
        regexp_replace(coalesce(content, ''), '<[^>]+>', ' '),  -- strip tags
        '&(nbsp|amp|lt|gt|quot|#39);', ' '),                     -- common entities
      '\\\\s+', ' ')) AS clean_text,
    date                                        AS raw_date,
    first_seen_at,
    last_seen_at
  FROM {catalog}.{schema}.raw_issues
)
SELECT
  document_id,
  source,
  source_type,
  region,
  bias,
  title,
  url,
  clean_text,
  -- exact text signals are extracted from and cited against
  trim(concat_ws('\\n\\n', title, clean_text))  AS full_text,
  coalesce(
    try_to_date(raw_date, 'MMM d, yyyy'),
    try_to_date(raw_date, 'MMMM d, yyyy'),
    try_to_date(raw_date, 'yyyy-MM-dd'),
    try_to_date(raw_date, 'MM/dd/yyyy'),
    try_to_date(left(raw_date, 10), 'yyyy-MM-dd'),
    to_date(first_seen_at)
  )                                             AS published_date,
  raw_date,
  -- stable key over normalized main text for a future incremental/MERGE path
  sha2(concat_ws('|', title, clean_text), 256)  AS content_hash,
  first_seen_at,
  last_seen_at
FROM cleaned
""")

# COMMAND ----------

n = spark.table(f"{catalog}.{schema}.documents").count()
print(f"documents: {n} rows")
display(
    spark.sql(
        f"SELECT document_id, source_type, region, published_date, length(full_text) AS full_len, title "
        f"FROM {catalog}.{schema}.documents ORDER BY full_len DESC LIMIT 10"
    )
)
