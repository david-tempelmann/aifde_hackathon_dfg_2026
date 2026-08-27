# Databricks notebook source
# MAGIC %md
# MAGIC # Silver 04 — signals, dimensions & bridges
# MAGIC Parse the raw extractions into the star schema (solution-design §5, Option A):
# MAGIC
# MAGIC - `issues` — controlled taxonomy dimension (seeded from `go_opps.vocab`).
# MAGIC - `places` — gazetteer dimension: territory seed (NY/CA/VA/US) + resolved extracted places.
# MAGIC - `signals` — the curated hub: one grounded, GO-relevant signal per (document, type).
# MAGIC - `signal_issues` / `signal_places` — bridge tables, each row carrying confidence + evidence.
# MAGIC
# MAGIC **Grounding gate:** a signal survives only if it is GO-relevant, meets the confidence
# MAGIC threshold, and its `supporting_quote` is a verbatim substring of the document — no
# MAGIC unsupported generated fact reaches the curated tables.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
dbutils.widgets.text("confidence_threshold", "")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

from go_opps.extraction import DEFAULT_CONFIDENCE_THRESHOLD
from go_opps.vocab import ISSUE_TAXONOMY, STATE_SEED

threshold = float(dbutils.widgets.get("confidence_threshold") or DEFAULT_CONFIDENCE_THRESHOLD)
print(f"confidence_threshold={threshold}")

# COMMAND ----------
# MAGIC %md ## Dimensions — issues (controlled vocab) & place seed

# COMMAND ----------

spark.createDataFrame(ISSUE_TAXONOMY, "issue_id string, label string, description string") \
    .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{catalog}.{schema}.issues")

# Seed the gazetteer; extracted places are unioned in below.
spark.createDataFrame(STATE_SEED, "place_id string, canonical_name string, state string, level string") \
    .createOrReplaceTempView("place_seed")

print("issues seeded:", spark.table(f"{catalog}.{schema}.issues").count())

# COMMAND ----------
# MAGIC %md ## Parse extractions & apply the grounding gate

# COMMAND ----------

# Schema mirrors go_opps.extraction.response_schema (inlined literal — from_json
# needs a constant schema, and there is no user input here).
_EXTRACTION_DDL = """
struct<
  is_go_relevant: boolean,
  signal_type: string,
  relevance_direction: string,
  issue_labels: array<string>,
  summary: string,
  affected_populations: array<string>,
  places: array<struct<name: string, level: string, state: string>>,
  organizations: array<string>,
  policies: array<string>,
  event_date: string,
  supporting_quote: string,
  why_go: string,
  confidence: double
>
"""

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW candidates AS
WITH parsed AS (
  SELECT e.chunk_id, e.document_id, from_json(e.response, '{_EXTRACTION_DDL}') AS s
  FROM {catalog}.{schema}.signal_extractions e
  WHERE e.response IS NOT NULL
),
joined AS (
  SELECT
    p.chunk_id, p.document_id, p.s,
    d.full_text, d.title, d.url, d.source, d.source_type, d.region, d.published_date,
    -- grounding: locate the verbatim quote in the document (1-based; 0 = not found)
    instr(d.full_text, p.s.supporting_quote) AS quote_pos
  FROM parsed p
  JOIN {catalog}.{schema}.documents d USING (document_id)
)
SELECT
  document_id, chunk_id, s, full_text, url, source, source_type, region, published_date,
  quote_pos
FROM joined
WHERE s.is_go_relevant = true
  AND s.confidence >= {threshold}
  AND length(trim(s.supporting_quote)) > 0
  AND quote_pos > 0                       -- drop ungrounded claims
""")

print("grounded GO-relevant candidates:", spark.table("candidates").count())

# COMMAND ----------
# MAGIC %md ## signals — dedup to one per (document, signal_type), highest confidence

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.signals AS
WITH ranked AS (
  SELECT
    sha2(concat_ws('|', document_id, s.signal_type), 256)          AS signal_id,
    document_id, chunk_id,
    s.signal_type                                                  AS signal_type,
    s.relevance_direction                                          AS relevance_direction,
    coalesce(try_to_date(s.event_date, 'yyyy-MM-dd'), published_date) AS event_date,
    s.summary                                                      AS summary,
    s.affected_populations                                         AS affected_populations,
    s.why_go                                                       AS why_go,
    s.supporting_quote                                             AS quote,
    (quote_pos - 1)                                                AS quote_char_start,
    (quote_pos - 1 + length(s.supporting_quote))                  AS quote_char_end,
    s.confidence                                                   AS confidence,
    region                                                         AS state,
    url, source, source_type, published_date,
    row_number() OVER (
      PARTITION BY document_id, s.signal_type ORDER BY s.confidence DESC
    ) AS rn
  FROM candidates
)
SELECT * EXCEPT (rn) FROM ranked WHERE rn = 1
""")

print("signals:", spark.table(f"{catalog}.{schema}.signals").count())

# COMMAND ----------
# MAGIC %md ## signal_issues bridge

# COMMAND ----------

# Explode controlled issue labels and map to issue_id via the issues dimension.
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.signal_issues AS
WITH exploded AS (
  SELECT
    sha2(concat_ws('|', c.document_id, c.s.signal_type), 256) AS signal_id,
    c.chunk_id                                                AS evidence_chunk_id,
    c.s.supporting_quote                                      AS evidence_quote,
    c.s.confidence                                            AS confidence,
    explode(c.s.issue_labels)                                 AS label,
    row_number() OVER (
      PARTITION BY c.document_id, c.s.signal_type ORDER BY c.s.confidence DESC
    ) AS rn
  FROM candidates c
)
SELECT DISTINCT e.signal_id, i.issue_id, e.confidence, e.evidence_chunk_id, e.evidence_quote
FROM exploded e
JOIN {catalog}.{schema}.issues i ON i.label = e.label
JOIN {catalog}.{schema}.signals s ON s.signal_id = e.signal_id   -- keep only surviving signals
WHERE e.rn = 1
""")

print("signal_issues:", spark.table(f"{catalog}.{schema}.signal_issues").count())

# COMMAND ----------
# MAGIC %md ## places dimension + signal_places bridge
# MAGIC Resolve each extracted place to a canonical `place_id`: territory states/nation collapse
# MAGIC onto the seed; anything finer gets a deterministic hashed id (lightweight canonicalization).

# COMMAND ----------

# place_id resolution (deterministic): nation/state territory → seed ids; else hashed.
_PLACE_ID = """
CASE
  WHEN pl.level = 'nation'
    OR lower(pl.name) IN ('united states','us','u.s.','usa','u.s.a.') THEN 'us'
  WHEN upper(pl.state) = 'NY' AND (pl.level = 'state' OR lower(pl.name) = 'new york') THEN 'state_ny'
  WHEN upper(pl.state) = 'CA' AND (pl.level = 'state' OR lower(pl.name) = 'california') THEN 'state_ca'
  WHEN upper(pl.state) = 'VA' AND (pl.level = 'state' OR lower(pl.name) = 'virginia') THEN 'state_va'
  ELSE concat('p_', substr(sha2(concat_ws('|', lower(trim(pl.name)), upper(coalesce(pl.state,''))), 256), 1, 12))
END
"""

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW resolved_places AS
SELECT
  sha2(concat_ws('|', c.document_id, c.s.signal_type), 256) AS signal_id,
  c.chunk_id                                                AS evidence_chunk_id,
  c.s.confidence                                            AS confidence,
  {_PLACE_ID}                                               AS place_id,
  trim(pl.name)                                             AS canonical_name,
  coalesce(nullif(upper(trim(pl.state)), ''), c.region)     AS state,
  pl.level                                                  AS level
FROM candidates c
LATERAL VIEW explode(c.s.places) t AS pl
WHERE length(trim(pl.name)) > 0
""")

# Dimension = territory seed ∪ resolved places not already in the seed.
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.places AS
SELECT place_id, canonical_name, state, level FROM place_seed
UNION
SELECT place_id, min(canonical_name) AS canonical_name, min(state) AS state, min(level) AS level
FROM resolved_places
WHERE place_id NOT IN (SELECT place_id FROM place_seed)
GROUP BY place_id
""")

# Bridge (dedup a place mentioned twice for one signal; keep highest confidence).
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.signal_places AS
SELECT signal_id, place_id, max(confidence) AS confidence, min(evidence_chunk_id) AS evidence_chunk_id
FROM resolved_places r
WHERE EXISTS (SELECT 1 FROM {catalog}.{schema}.signals s WHERE s.signal_id = r.signal_id)
GROUP BY signal_id, place_id
""")

print("places:", spark.table(f"{catalog}.{schema}.places").count())
print("signal_places:", spark.table(f"{catalog}.{schema}.signal_places").count())

# COMMAND ----------
# MAGIC %md ## organizations & policies dimensions + bridges (Could-have NER)
# MAGIC The extraction already captured named orgs and bills/policies per signal; here we
# MAGIC canonicalize them deterministically — lowercase, strip punctuation, collapse
# MAGIC whitespace → a `norm_key` that merges surface variants — and keep the most frequent
# MAGIC surface form as the display name. Fuzzy alias resolution is a later refinement.

# COMMAND ----------

# Shared builder: explode a string-array NER field from `candidates` into a
# dimension (id + canonical_name) and a bridge (signal_id + id + confidence +
# evidence), keeping only entities attached to a surviving signal.
def build_ner(field: str, id_prefix: str, dim_table: str, bridge_table: str, id_col: str):
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW _ner_{field} AS
    SELECT
      sha2(concat_ws('|', c.document_id, c.s.signal_type), 256)          AS signal_id,
      c.chunk_id                                                          AS evidence_chunk_id,
      c.s.confidence                                                      AS confidence,
      trim(name)                                                          AS name,
      trim(regexp_replace(lower(trim(name)), '[^a-z0-9]+', ' '))          AS norm_key
    FROM candidates c
    LATERAL VIEW explode(c.s.{field}) t AS name
    WHERE length(trim(name)) > 0
      AND length(trim(regexp_replace(lower(trim(name)), '[^a-z0-9]+', ' '))) > 0
      AND EXISTS (SELECT 1 FROM {catalog}.{schema}.signals s WHERE s.signal_id = sha2(concat_ws('|', c.document_id, c.s.signal_type), 256))
    """)

    # Dimension: one row per norm_key, display name = most frequent surface form.
    spark.sql(f"""
    CREATE OR REPLACE TABLE {catalog}.{schema}.{dim_table} AS
    WITH counts AS (
      SELECT norm_key, name, count(*) c FROM _ner_{field} GROUP BY norm_key, name
    ),
    ranked AS (
      SELECT norm_key, name,
             row_number() OVER (PARTITION BY norm_key ORDER BY c DESC, length(name) DESC) rn
      FROM counts
    )
    SELECT concat('{id_prefix}', substr(sha2(norm_key, 256), 1, 12)) AS {id_col},
           name AS canonical_name
    FROM ranked WHERE rn = 1
    """)

    # Bridge: dedup an entity mentioned across overlapping chunks for one signal.
    spark.sql(f"""
    CREATE OR REPLACE TABLE {catalog}.{schema}.{bridge_table} AS
    SELECT signal_id,
           concat('{id_prefix}', substr(sha2(norm_key, 256), 1, 12)) AS {id_col},
           max(confidence)          AS confidence,
           min(evidence_chunk_id)   AS evidence_chunk_id
    FROM _ner_{field}
    GROUP BY signal_id, concat('{id_prefix}', substr(sha2(norm_key, 256), 1, 12))
    """)


build_ner("organizations", "org_", "organizations", "signal_orgs", "org_id")
build_ner("policies", "pol_", "policies", "signal_policies", "policy_id")

print("organizations:", spark.table(f"{catalog}.{schema}.organizations").count(),
      "| signal_orgs:", spark.table(f"{catalog}.{schema}.signal_orgs").count())
print("policies:", spark.table(f"{catalog}.{schema}.policies").count(),
      "| signal_policies:", spark.table(f"{catalog}.{schema}.signal_policies").count())

# COMMAND ----------
# MAGIC %md ## Sanity check — a few signals with issue + place

# COMMAND ----------

display(spark.sql(f"""
SELECT s.signal_id, s.signal_type, s.relevance_direction, s.state, s.confidence,
       i.label AS issue, s.summary, left(s.quote, 120) AS quote
FROM {catalog}.{schema}.signals s
LEFT JOIN {catalog}.{schema}.signal_issues si ON si.signal_id = s.signal_id
LEFT JOIN {catalog}.{schema}.issues i ON i.issue_id = si.issue_id
ORDER BY s.confidence DESC
LIMIT 20
"""))
