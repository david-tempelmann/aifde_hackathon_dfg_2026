# Databricks notebook source
# MAGIC %md
# MAGIC # Silver 03 — extract (AI Functions)
# MAGIC One `ai_query` per chunk with a **strict JSON response schema** → a fully-grounded
# MAGIC signal record in a single pass (classify + relevance + issue label + geography +
# MAGIC verbatim supporting quote). See `go_opps.extraction` for the instruction and schema.
# MAGIC
# MAGIC This is the **raw landing table** — every chunk gets a row (relevant or not, parsed
# MAGIC or errored). Filtering, grounding-verification, and normalization happen in 04.
# MAGIC `failOnError => false` keeps one bad row from failing the whole batch.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
dbutils.widgets.text("model", "")
# sample_per_type > 0 restricts extraction to N documents per source_type (a cheap,
# representative smoke test across news/government/social/...). 0 = full corpus.
dbutils.widgets.text("sample_per_type", "0")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
sample_per_type = int(dbutils.widgets.get("sample_per_type"))

from go_opps.extraction import DEFAULT_MODEL, INSTRUCTION, response_format_json

model = dbutils.widgets.get("model") or DEFAULT_MODEL
rformat = response_format_json()
print(f"Extracting with model={model}, sample_per_type={sample_per_type or 'ALL'}")

# COMMAND ----------

# Chunk set to extract over. When sampling, take the first N documents per
# source_type (deterministic) so the smoke test spans every kind of source.
if sample_per_type > 0:
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW _chunk_source AS
    WITH sampled_docs AS (
      SELECT document_id FROM (
        SELECT document_id,
               row_number() OVER (PARTITION BY source_type ORDER BY document_id) AS rn
        FROM {catalog}.{schema}.silver_documents
      ) WHERE rn <= {sample_per_type}
    )
    SELECT c.* FROM {catalog}.{schema}.silver_chunks c
    JOIN sampled_docs USING (document_id)
    """)
else:
    spark.sql(f"CREATE OR REPLACE TEMP VIEW _chunk_source AS SELECT * FROM {catalog}.{schema}.silver_chunks")

print("chunks to extract:", spark.table("_chunk_source").count())

# COMMAND ----------

# ai_query first arg (endpoint) is inlined as a literal; the long instruction and
# the response-format schema pass as parameter markers so we avoid SQL-escaping a
# multi-line prompt. failOnError => false makes ai_query return
# STRUCT<result, errorMessage> — we split those into columns for observability.
spark.sql(
    f"""
    CREATE OR REPLACE TABLE {catalog}.{schema}.silver_signal_extractions AS
    WITH raw AS (
      SELECT
        c.chunk_id,
        c.document_id,
        ai_query(
          '{model}',
          concat(:instruction, '\\n\\n---\\nTITLE: ', coalesce(d.title, ''), '\\nTEXT:\\n', c.text),
          failOnError => false,
          responseFormat => :rformat
        ) AS resp
      FROM _chunk_source c
      JOIN {catalog}.{schema}.silver_documents d USING (document_id)
    )
    SELECT
      chunk_id,
      document_id,
      '{model}'              AS model,
      resp.result           AS response,
      resp.errorMessage     AS error_message,
      current_timestamp()   AS extracted_at
    FROM raw
    """,
    args={"instruction": INSTRUCTION, "rformat": rformat},
)

# COMMAND ----------

total = spark.table(f"{catalog}.{schema}.silver_signal_extractions").count()
errors = spark.sql(
    f"SELECT count(*) c FROM {catalog}.{schema}.silver_signal_extractions WHERE error_message IS NOT NULL"
).collect()[0]["c"]
print(f"signal_extractions: {total} rows, {errors} errored")
display(
    spark.sql(
        f"SELECT chunk_id, left(response, 300) AS response_preview, error_message "
        f"FROM {catalog}.{schema}.silver_signal_extractions LIMIT 5"
    )
)
