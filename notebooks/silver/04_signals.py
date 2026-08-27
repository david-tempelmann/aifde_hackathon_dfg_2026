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
from go_opps.vocab import ISSUE_TAXONOMY

threshold = float(dbutils.widgets.get("confidence_threshold") or DEFAULT_CONFIDENCE_THRESHOLD)
print(f"confidence_threshold={threshold}")

# COMMAND ----------
# MAGIC %md ## Dimensions — issues (controlled vocab) & place seed

# COMMAND ----------

spark.createDataFrame(ISSUE_TAXONOMY, "issue_id string, label string, description string") \
    .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{catalog}.{schema}.silver_issues")

print("issues seeded:", spark.table(f"{catalog}.{schema}.silver_issues").count())

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

# US states/territories OUTSIDE the NY/CA/VA scope. If a signal's extracted
# geography points at one of these, we don't force it into a territory — we label
# it OTHER. (Names and 2-letter codes; excludes CA/NY/VA and the national 'US'.)
_OTHER_STATE_NAMES = [
    "alabama", "alaska", "arizona", "arkansas", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
    "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas",
    "utah", "vermont", "washington", "west virginia", "wisconsin", "wyoming",
]
_OTHER_STATE_CODES = [
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "WA", "WV",
    "WI", "WY",
]
_OTHER_NAMES_SQL = ", ".join(f"'{n}'" for n in _OTHER_STATE_NAMES)
_OTHER_CODES_SQL = ", ".join(f"'{c}'" for c in _OTHER_STATE_CODES)

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW candidates AS
WITH parsed AS (
  SELECT e.chunk_id, e.document_id, from_json(e.response, '{_EXTRACTION_DDL}') AS s
  FROM {catalog}.{schema}.silver_signal_extractions e
  WHERE e.response IS NOT NULL
),
joined AS (
  SELECT
    p.chunk_id, p.document_id, p.s,
    d.full_text, d.title, d.url, d.source, d.source_type, d.region, d.published_date,
    -- grounding: locate the verbatim quote in the document (1-based; 0 = not found)
    instr(d.full_text, p.s.supporting_quote) AS quote_pos
  FROM parsed p
  JOIN {catalog}.{schema}.silver_documents d USING (document_id)
)
SELECT
  document_id, chunk_id, s, full_text, url, source, source_type, region, published_date,
  quote_pos,
  -- territory state(s) the *content* is about, inferred from extracted places
  -- (model-provided state code, or a state name). Distinct from `region`, which
  -- is only where we scraped the item — unreliable as geography for e.g. social posts.
  filter(transform(s.places, x ->
    CASE
      WHEN upper(coalesce(x.state, '')) IN ('NY','CA','VA') THEN upper(x.state)
      WHEN lower(trim(x.name)) = 'california'                THEN 'CA'
      WHEN lower(trim(x.name)) IN ('new york','new york state','new york city') THEN 'NY'
      WHEN lower(trim(x.name)) = 'virginia'                  THEN 'VA'
      ELSE NULL
    END), y -> y IS NOT NULL) AS terr_states,
  -- does the content name a place clearly OUTSIDE the NY/CA/VA territory?
  exists(s.places, x ->
    lower(trim(x.name)) IN ({_OTHER_NAMES_SQL})
    OR upper(coalesce(x.state, '')) IN ({_OTHER_CODES_SQL})
  ) AS other_geo
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
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_signals AS
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
    -- subject territory. Use a territory (NY/CA/VA) only with evidence; otherwise
    -- OTHER, so out-of-territory / ambiguous content isn't force-grouped:
    --  1. scrape region corroborated by the content's geography  -> region
    --  2. content clearly about a single territory state (no out-of-territory place) -> that state
    --  3. region is a territory/US and the content contradicts nothing -> region
    --  4. otherwise -> OTHER
    CASE
      WHEN array_contains(terr_states, region) THEN region
      WHEN size(array_distinct(terr_states)) = 1 AND NOT other_geo
        THEN try_element_at(array_distinct(terr_states), 1)
      -- fall back to the scrape region only for region-reliable sources
      -- (state portals, local news). Social/aggregated posts get their region
      -- from where we scraped, not what they discuss -> don't trust it.
      WHEN source_type NOT IN ('social', 'news-aggregated')
        AND region IN ('NY','CA','VA','US') AND size(terr_states) = 0 AND NOT other_geo THEN region
      ELSE 'OTHER'
    END                                                            AS state,
    region                                                         AS source_region,
    url, source, source_type, published_date,
    row_number() OVER (
      PARTITION BY document_id, s.signal_type ORDER BY s.confidence DESC
    ) AS rn
  FROM candidates
)
SELECT * EXCEPT (rn) FROM ranked WHERE rn = 1
""")

print("signals:", spark.table(f"{catalog}.{schema}.silver_signals").count())

# COMMAND ----------
# MAGIC %md ## signal_issues bridge

# COMMAND ----------

# A signal can concern MULTIPLE issues (issue_labels is an array). Pick the
# winning chunk per (document, signal_type) FIRST, then explode ITS labels — so
# we keep every issue of the chosen chunk (the earlier version ranked *after*
# exploding, which collapsed each signal to a single issue).
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_signal_issues AS
WITH winning AS (
  SELECT c.*,
         row_number() OVER (
           PARTITION BY c.document_id, c.s.signal_type ORDER BY c.s.confidence DESC
         ) AS rn
  FROM candidates c
),
exploded AS (
  SELECT
    sha2(concat_ws('|', document_id, s.signal_type), 256) AS signal_id,
    chunk_id                                              AS evidence_chunk_id,
    s.supporting_quote                                    AS evidence_quote,
    s.confidence                                          AS confidence,
    explode(s.issue_labels)                               AS label
  FROM winning WHERE rn = 1
)
SELECT DISTINCT e.signal_id, i.issue_id, e.confidence, e.evidence_chunk_id, e.evidence_quote
FROM exploded e
JOIN {catalog}.{schema}.silver_issues i ON i.label = e.label
JOIN {catalog}.{schema}.silver_signals s ON s.signal_id = e.signal_id
""")

print("signal_issues:", spark.table(f"{catalog}.{schema}.silver_signal_issues").count())

# COMMAND ----------
# MAGIC %md ## places dimension + signal_places bridge (FIPS gazetteer resolution)
# MAGIC Resolve each extracted place to a canonical **FIPS `geoid`** via `silver_ref_place_alias`
# MAGIC (built by `notebooks/reference/00_gazetteer.py`). Scope the match by the place's own state
# MAGIC hint or the signal's state; fall back to a nationally-unique alias. County beats city on a
# MAGIC shared name, so "San Diego"/"San Diego County"/"City of San Diego" collapse to one place_id.
# MAGIC Unmatched names keep a stable `u_<hash>` id marked `unresolved`.

# COMMAND ----------

from go_opps.resolution import normalize_place_name

spark.udf.register("normalize_place", normalize_place_name, "string")

# aliases that are unambiguous across the whole gazetteer (one geoid) — used when
# we have no state to scope by (e.g. an OTHER/US signal that names a place).
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _alias_unique AS
SELECT alias_norm, first(geoid) geoid, first(canonical_name) canonical_name, first(level) level
FROM {catalog}.{schema}.silver_ref_place_alias
GROUP BY alias_norm HAVING count(DISTINCT geoid) = 1
""")

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW resolved_places AS
WITH exploded AS (
  SELECT
    sha2(concat_ws('|', c.document_id, c.s.signal_type), 256) AS signal_id,
    c.chunk_id                                                AS evidence_chunk_id,
    c.s.confidence                                            AS confidence,
    trim(pl.name)                                             AS raw_name,
    normalize_place(pl.name)                                  AS alias_norm,
    -- scope: place's own state hint (model code / territory name), else the
    -- signal's territory state; NULL for OTHER/US signals.
    coalesce(
      CASE WHEN upper(trim(coalesce(pl.state, ''))) IN ('NY','CA','VA') THEN upper(trim(pl.state)) END,
      CASE WHEN lower(trim(pl.name)) = 'california' THEN 'CA'
           WHEN lower(trim(pl.name)) IN ('new york','new york state','new york city') THEN 'NY'
           WHEN lower(trim(pl.name)) = 'virginia' THEN 'VA' END,
      CASE WHEN s2.state IN ('NY','CA','VA') THEN s2.state END
    )                                                         AS scope_usps
  FROM candidates c
  JOIN {catalog}.{schema}.silver_signals s2
    ON s2.signal_id = sha2(concat_ws('|', c.document_id, c.s.signal_type), 256)
  LATERAL VIEW explode(c.s.places) t AS pl
  WHERE length(trim(pl.name)) > 0
)
SELECT
  e.signal_id, e.evidence_chunk_id, e.confidence, e.raw_name, e.alias_norm,
  coalesce(a.geoid, u.geoid, concat('u_', substr(sha2(e.alias_norm, 256), 1, 12))) AS place_id,
  coalesce(a.canonical_name, u.canonical_name, initcap(e.raw_name))                AS canonical_name,
  coalesce(a.level, u.level, 'unresolved')                                         AS level,
  coalesce(a.usps, e.scope_usps)                                                   AS state
FROM exploded e
LEFT JOIN {catalog}.{schema}.silver_ref_place_alias a
  ON a.alias_norm = e.alias_norm AND a.usps = e.scope_usps
LEFT JOIN _alias_unique u
  ON u.alias_norm = e.alias_norm AND a.geoid IS NULL
WHERE length(e.alias_norm) > 0
""")

# Dimension: distinct resolved places, enriched with the gazetteer hierarchy.
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_places AS
WITH d AS (SELECT DISTINCT place_id, canonical_name, level, state FROM resolved_places),
enriched AS (
  SELECT d.place_id,
         coalesce(g.canonical_name, d.canonical_name) AS canonical_name,
         coalesce(g.level, d.level)                   AS level,
         coalesce(g.usps, d.state)                    AS state,
         g.parent_geoid                               AS parent_geoid
  FROM d LEFT JOIN {catalog}.{schema}.silver_ref_gazetteer g ON g.geoid = d.place_id
)
-- one row per place_id (the pre-join DISTINCT can leave dupes that the gazetteer
-- join then normalizes to identical rows, e.g. 'us')
SELECT place_id, max(canonical_name) AS canonical_name, max(level) AS level,
       max(state) AS state, max(parent_geoid) AS parent_geoid
FROM enriched GROUP BY place_id
""")

# Bridge (dedup a place mentioned twice for one signal; keep highest confidence).
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_signal_places AS
SELECT signal_id, place_id, max(confidence) AS confidence, min(evidence_chunk_id) AS evidence_chunk_id
FROM resolved_places
GROUP BY signal_id, place_id
""")

print("places:", spark.table(f"{catalog}.{schema}.silver_places").count())
print("signal_places:", spark.table(f"{catalog}.{schema}.silver_signal_places").count())

# COMMAND ----------
# MAGIC %md ## organizations & policies dimensions + bridges (NER + resolution)
# MAGIC Deterministic entity resolution (`go_opps.resolution`): bill-number normalization
# MAGIC (`A.B. 2376 (Bains)` → `AB 2376`, state-qualified), named-program aliases (ACA, SNAP…),
# MAGIC and org acronym-linking (`… Services (DHCS)` binds standalone `DHCS`). Surface variants
# MAGIC collapse to one id; unmatched entities get a stable hashed fallback.

# COMMAND ----------

from go_opps.resolution import resolve_org_surfaces, resolve_policy

_signal_id = "sha2(concat_ws('|', c.document_id, c.s.signal_type), 256)"


def _explode_ner(field: str, extra_cols: str = "") -> None:
    """Explode a NER array field into (signal_id, evidence, surface[, state]) for
    surviving signals only."""
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW _ner_{field} AS
    SELECT {_signal_id} AS signal_id, c.chunk_id AS evidence_chunk_id,
           c.s.confidence AS confidence, trim(name) AS surface {extra_cols}
    FROM candidates c
    LATERAL VIEW explode(c.s.{field}) t AS name
    WHERE length(trim(name)) > 0
      AND EXISTS (SELECT 1 FROM {catalog}.{schema}.silver_signals s WHERE s.signal_id = {_signal_id})
    """)


# --- organizations: resolve distinct surfaces on the driver (acronym linking) --
_explode_ner("organizations")
org_counts = {r["surface"]: r["n"] for r in
              spark.sql("SELECT surface, count(*) n FROM _ner_organizations GROUP BY surface").collect()}
org_map = resolve_org_surfaces(org_counts)  # surface -> (org_id, canonical_name, method)
spark.createDataFrame(
    [(s, v[0], v[1], v[2]) for s, v in org_map.items()],
    "surface string, org_id string, canonical_name string, match_method string",
).createOrReplaceTempView("_org_map")

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_organizations AS
SELECT org_id, max(canonical_name) AS canonical_name,
       array_sort(collect_set(surface)) AS aliases, min(match_method) AS match_method
FROM _org_map GROUP BY org_id
""")
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_signal_orgs AS
SELECT e.signal_id, m.org_id, max(e.confidence) AS confidence, min(e.evidence_chunk_id) AS evidence_chunk_id
FROM _ner_organizations e JOIN _org_map m USING (surface)
GROUP BY e.signal_id, m.org_id
""")

# --- policies: bill-number / alias resolution, state-qualified per signal --------
# (joins silver_signals for the subject state used to qualify bill codes)
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _ner_policies AS
SELECT {_signal_id} AS signal_id, c.chunk_id AS evidence_chunk_id, c.s.confidence AS confidence,
       trim(name) AS surface, s2.state AS state
FROM candidates c
JOIN {catalog}.{schema}.silver_signals s2 ON s2.signal_id = {_signal_id}
LATERAL VIEW explode(c.s.policies) t AS name
WHERE length(trim(name)) > 0
""")
pol_pairs = spark.sql("SELECT DISTINCT surface, state FROM _ner_policies").collect()
pol_map = [(r["surface"], r["state"], *resolve_policy(r["surface"], r["state"])) for r in pol_pairs]
spark.createDataFrame(
    pol_map, "surface string, state string, policy_id string, canonical_name string, match_method string"
).createOrReplaceTempView("_pol_map")

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_policies AS
SELECT policy_id, max(canonical_name) AS canonical_name,
       array_sort(collect_set(surface)) AS aliases, min(match_method) AS match_method
FROM _pol_map GROUP BY policy_id
""")
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_signal_policies AS
SELECT e.signal_id, m.policy_id, max(e.confidence) AS confidence, min(e.evidence_chunk_id) AS evidence_chunk_id
FROM _ner_policies e JOIN _pol_map m ON e.surface = m.surface AND e.state <=> m.state
GROUP BY e.signal_id, m.policy_id
""")

print("organizations:", spark.table(f"{catalog}.{schema}.silver_organizations").count(),
      "| signal_orgs:", spark.table(f"{catalog}.{schema}.silver_signal_orgs").count())
print("policies:", spark.table(f"{catalog}.{schema}.silver_policies").count(),
      "| signal_policies:", spark.table(f"{catalog}.{schema}.silver_signal_policies").count())

# COMMAND ----------
# MAGIC %md ## Sanity check — a few signals with issue + place

# COMMAND ----------

display(spark.sql(f"""
SELECT s.signal_id, s.signal_type, s.relevance_direction, s.state, s.confidence,
       i.label AS issue, s.summary, left(s.quote, 120) AS quote
FROM {catalog}.{schema}.silver_signals s
LEFT JOIN {catalog}.{schema}.silver_signal_issues si ON si.signal_id = s.signal_id
LEFT JOIN {catalog}.{schema}.silver_issues i ON i.issue_id = si.issue_id
ORDER BY s.confidence DESC
LIMIT 20
"""))
