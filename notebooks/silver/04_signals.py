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
dbutils.widgets.text("canon_model", "")
dbutils.widgets.text("event_model", "")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

from go_opps.canonicalize import DEFAULT_CANON_MODEL
from go_opps.events import DEFAULT_EVENT_MODEL
from go_opps.extraction import DEFAULT_CONFIDENCE_THRESHOLD
from go_opps.vocab import ISSUE_TAXONOMY

threshold = float(dbutils.widgets.get("confidence_threshold") or DEFAULT_CONFIDENCE_THRESHOLD)
canon_model = dbutils.widgets.get("canon_model") or DEFAULT_CANON_MODEL
event_model = dbutils.widgets.get("event_model") or DEFAULT_EVENT_MODEL
print(f"confidence_threshold={threshold}, canon_model={canon_model}, event_model={event_model}")

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
  source_confidence: double,
  overall_confidence: double
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
  AND s.overall_confidence >= {threshold}
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
    -- overall_confidence is the anchor (keeps the `confidence` column that gold
    -- and the app read); source_confidence rides along as a trust diagnostic.
    s.overall_confidence                                           AS confidence,
    s.source_confidence                                            AS source_confidence,
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
      PARTITION BY document_id, s.signal_type ORDER BY s.overall_confidence DESC
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
           PARTITION BY c.document_id, c.s.signal_type ORDER BY c.s.overall_confidence DESC
         ) AS rn
  FROM candidates c
),
exploded AS (
  SELECT
    sha2(concat_ws('|', document_id, s.signal_type), 256) AS signal_id,
    chunk_id                                              AS evidence_chunk_id,
    s.supporting_quote                                    AS evidence_quote,
    s.overall_confidence                                  AS confidence,
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
    c.s.overall_confidence                                    AS confidence,
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
         g.parent_geoid                               AS parent_geoid,
         g.lat                                        AS lat,
         g.lon                                        AS lon
  FROM d LEFT JOIN {catalog}.{schema}.silver_ref_gazetteer g ON g.geoid = d.place_id
)
-- one row per place_id (the pre-join DISTINCT can leave dupes that the gazetteer
-- join then normalizes to identical rows, e.g. 'us'). Unresolved (u_<hash>) places
-- have no gazetteer match, so lat/lon are null (no map pin) — expected.
SELECT place_id, max(canonical_name) AS canonical_name, max(level) AS level,
       max(state) AS state, max(parent_geoid) AS parent_geoid,
       max(lat) AS lat, max(lon) AS lon
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
# MAGIC %md ## organizations & policies — LLM canonicalization + bridges
# MAGIC Open-ended entities (agencies, committees, nonprofits; bills, programs) are canonicalized
# MAGIC by an LLM (`go_opps.canonicalize`): one `ai_query` batch per kind clusters the *distinct*
# MAGIC surface strings into real-world entities, merging acronyms, abbreviations, and
# MAGIC state-qualified / descriptive variants a rule set can't scale to (no hand-kept alias seed).
# MAGIC The **canonical id is ours** — a stable hash of the model's canonical name, never the
# MAGIC model's own — so ids stay deterministic across the full-reprocess pipeline; any surface the
# MAGIC model drops falls back to a per-surface id (`llm_unassigned`). Each dimension also carries
# MAGIC `entity_type` and `match_confidence`.

# COMMAND ----------

import json

from go_opps.canonicalize import (
    assign_ids,
    build_instruction,
    build_payload,
    response_format_json,
)

_signal_id = "sha2(concat_ws('|', c.document_id, c.s.signal_type), 256)"


def _cluster(kind: str, items: list[tuple[int, str, int]]) -> list[dict]:
    """One ai_query batch over the distinct surfaces → the model's clusters."""
    if not items:
        return []
    resp = spark.sql(
        f"""
        SELECT ai_query(
          '{canon_model}',
          concat(:instr, '\\n\\nITEMS:\\n', :payload),
          failOnError => false,
          responseFormat => :rformat
        ) AS resp
        """,
        args={
            "instr": build_instruction(kind),
            "payload": build_payload(items),
            "rformat": response_format_json(kind),
        },
    ).collect()[0]["resp"]
    if resp["errorMessage"]:
        raise RuntimeError(f"canonicalization ai_query failed for {kind}: {resp['errorMessage']}")
    return json.loads(resp["result"])["clusters"]


def canonicalize_ner(kind: str, id_col: str, dim_table: str, bridge_table: str) -> None:
    """Explode a NER array over surviving signals, LLM-cluster the distinct surfaces to
    deterministic ids, then build the dimension (+ aliases / type / confidence) and bridge."""
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW _ner_{kind} AS
    SELECT {_signal_id} AS signal_id, c.chunk_id AS evidence_chunk_id,
           c.s.overall_confidence AS confidence, trim(name) AS surface
    FROM candidates c
    LATERAL VIEW explode(c.s.{kind}) t AS name
    WHERE length(trim(name)) > 0
      AND EXISTS (SELECT 1 FROM {catalog}.{schema}.silver_signals s WHERE s.signal_id = {_signal_id})
    """)

    rows = spark.sql(
        f"SELECT surface, count(*) AS n FROM _ner_{kind} GROUP BY surface ORDER BY n DESC, surface"
    ).collect()
    items = [(i, r["surface"], r["n"]) for i, r in enumerate(rows)]
    dims, maps = assign_ids(_cluster(kind, items), items, kind)

    _dim_ddl = ("id string, canonical_name string, entity_type string, "
                "match_method string, match_confidence double")
    spark.createDataFrame(dims or [], _dim_ddl).createOrReplaceTempView(f"_{kind}_dim")
    spark.createDataFrame(maps or [], "surface string, id string").createOrReplaceTempView(f"_{kind}_map")

    spark.sql(f"""
    CREATE OR REPLACE TABLE {catalog}.{schema}.{dim_table} AS
    SELECT d.id AS {id_col}, d.canonical_name, d.entity_type,
           array_sort(collect_set(m.surface)) AS aliases,
           d.match_method, d.match_confidence
    FROM _{kind}_dim d LEFT JOIN _{kind}_map m ON m.id = d.id
    GROUP BY d.id, d.canonical_name, d.entity_type, d.match_method, d.match_confidence
    """)

    spark.sql(f"""
    CREATE OR REPLACE TABLE {catalog}.{schema}.{bridge_table} AS
    SELECT e.signal_id, m.id AS {id_col},
           max(e.confidence) AS confidence, min(e.evidence_chunk_id) AS evidence_chunk_id
    FROM _ner_{kind} e JOIN _{kind}_map m USING (surface)
    GROUP BY e.signal_id, m.id
    """)


canonicalize_ner("organizations", "org_id", "silver_organizations", "silver_signal_orgs")
canonicalize_ner("policies", "policy_id", "silver_policies", "silver_signal_policies")

print("organizations:", spark.table(f"{catalog}.{schema}.silver_organizations").count(),
      "| signal_orgs:", spark.table(f"{catalog}.{schema}.silver_signal_orgs").count())
print("policies:", spark.table(f"{catalog}.{schema}.silver_policies").count(),
      "| signal_policies:", spark.table(f"{catalog}.{schema}.silver_signal_policies").count())

# COMMAND ----------
# MAGIC %md ## events — collapse same-event duplicate signals across documents
# MAGIC One real-world event scraped as several documents yields near-duplicate signals (e.g. a
# MAGIC San Diego heat warning from 6 NWS feeds → 6 `emergency/risk/CA` signals). We group them
# MAGIC with **LLM clustering** (`go_opps.events`): each signal is described by its document
# MAGIC **title + location + date + type**; one `ai_query` batch groups the signals that describe
# MAGIC the same real-world event. As with org/policy canonicalization, the **LLM decides
# MAGIC membership** and **we assign the `event_id` deterministically** (a hash of the model's
# MAGIC canonical event label); any signal it drops falls back to its own singleton event.
# MAGIC
# MAGIC `title`+`location` are the primary evidence; `date` is guidance, not a hard rule, so the
# MAGIC same event across adjacent days merges while different-date instances stay apart —
# MAGIC something a rigid deterministic key can't do. `event_id` + `primary_place_geoid` are added
# MAGIC onto `silver_signals`; `silver_events` is the collapsed dimension (member/source/doc counts
# MAGIC + a representative signal), so duplicate scraping becomes a corroboration count.

# COMMAND ----------

import json

from go_opps import events as ev

# Finest resolved place per signal (lowest level wins; unresolved ranked last) — used both
# as the clustering `location` descriptor and for primary_place_geoid on signals/events.
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _signal_primary_place AS
WITH ranked AS (
  SELECT sp.signal_id, p.place_id, p.canonical_name, p.state,
         row_number() OVER (
           PARTITION BY sp.signal_id
           ORDER BY CASE p.level WHEN 'place'  THEN 0 WHEN 'county' THEN 1
                                 WHEN 'state'  THEN 2 WHEN 'nation' THEN 3 ELSE 4 END,
                    p.place_id
         ) AS rn
  FROM {catalog}.{schema}.silver_signal_places sp
  JOIN {catalog}.{schema}.silver_places p USING (place_id)
)
SELECT signal_id, place_id AS primary_place_geoid, canonical_name AS primary_place_name, state
FROM ranked WHERE rn = 1
""")

# One descriptor per signal: title (from the source document) + location + date + type.
descriptor_rows = spark.sql(f"""
SELECT s.signal_id,
       coalesce(d.title, '')                                   AS title,
       coalesce(pp.primary_place_name, s.state)                AS location,
       coalesce(cast(s.event_date AS string), '')              AS date,
       s.signal_type                                           AS type
FROM {catalog}.{schema}.silver_signals s
LEFT JOIN {catalog}.{schema}.silver_documents d USING (document_id)
LEFT JOIN _signal_primary_place pp USING (signal_id)
""").collect()
items = [
    {"id": i, "signal_id": r["signal_id"], "title": r["title"],
     "location": r["location"], "date": r["date"], "type": r["type"]}
    for i, r in enumerate(descriptor_rows)
]


def _cluster_events(items: list[dict]) -> list[dict]:
    """One ai_query batch groups the signals into events."""
    if not items:
        return []
    resp = spark.sql(
        f"""
        SELECT ai_query(
          '{event_model}',
          concat(:instr, '\\n\\nSIGNALS:\\n', :payload),
          failOnError => false,
          responseFormat => :rformat
        ) AS resp
        """,
        args={
            "instr": ev.build_instruction(),
            "payload": ev.build_payload(items),
            "rformat": ev.response_format_json(),
        },
    ).collect()[0]["resp"]
    if resp["errorMessage"]:
        raise RuntimeError(f"event clustering ai_query failed: {resp['errorMessage']}")
    return json.loads(resp["result"])["clusters"]


events_rows, signal_event_rows = ev.assign_event_ids(_cluster_events(items), items)
spark.createDataFrame(
    events_rows or [],
    "event_id string, canonical_label string, match_method string, match_confidence double",
).createOrReplaceTempView("_event_labels")
spark.createDataFrame(signal_event_rows or [], "signal_id string, event_id string") \
    .createOrReplaceTempView("_signal_event")

# Event dimension: aggregate members + a representative signal (highest confidence, lowest
# id); event-level display fields (type/direction/place) come from that representative.
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.silver_events AS
WITH members AS (
  SELECT se.event_id, s.*, pp.primary_place_geoid, pp.primary_place_name
  FROM _signal_event se
  JOIN {catalog}.{schema}.silver_signals s USING (signal_id)
  LEFT JOIN _signal_primary_place pp USING (signal_id)
),
agg AS (
  SELECT event_id,
         count(*)                    AS signal_count,
         count(DISTINCT document_id) AS document_count,
         count(DISTINCT source)      AS source_count,
         max(confidence)             AS confidence,
         min(event_date)             AS event_date_min,
         max(event_date)             AS event_date_max
  FROM members GROUP BY event_id
),
rep AS (
  SELECT event_id, signal_id AS rep_signal_id, signal_type, relevance_direction,
         primary_place_geoid, primary_place_name,
         summary AS rep_summary, why_go AS rep_why_go, url AS rep_url
  FROM (
    SELECT m.*, row_number() OVER (
             PARTITION BY event_id ORDER BY confidence DESC, signal_id) AS rn
    FROM members m
  ) WHERE rn = 1
)
SELECT a.event_id, l.canonical_label, r.signal_type, r.relevance_direction,
       r.primary_place_geoid, r.primary_place_name,
       a.event_date_min, a.event_date_max,
       a.signal_count, a.document_count, a.source_count, a.confidence,
       l.match_method, l.match_confidence,
       r.rep_signal_id, r.rep_summary, r.rep_why_go, r.rep_url
FROM agg a
JOIN rep r USING (event_id)
LEFT JOIN _event_labels l USING (event_id)
""")

# Add event_id + primary_place_geoid onto silver_signals. Staged via a scratch table so we
# never read and overwrite silver_signals in one statement. (04 always rebuilds silver_signals
# fresh above, so s.* has no event_id yet — this appends it exactly once per full run.)
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}._stage_signals AS
SELECT s.*, se.event_id,
       coalesce(pp.primary_place_geoid, concat('state:', s.state)) AS primary_place_geoid
FROM {catalog}.{schema}.silver_signals s
LEFT JOIN _signal_event se USING (signal_id)
LEFT JOIN _signal_primary_place pp USING (signal_id)
""")
spark.sql(f"CREATE OR REPLACE TABLE {catalog}.{schema}.silver_signals AS "
          f"SELECT * FROM {catalog}.{schema}._stage_signals")
spark.sql(f"DROP TABLE IF EXISTS {catalog}.{schema}._stage_signals")

n_events = spark.table(f"{catalog}.{schema}.silver_events").count()
n_signals = spark.table(f"{catalog}.{schema}.silver_signals").count()
n_collapsed = spark.sql(
    f"SELECT count(*) c FROM {catalog}.{schema}.silver_events WHERE signal_count > 1"
).collect()[0]["c"]
print(f"events: {n_events} (from {n_signals} signals; {n_collapsed} multi-signal events)")
display(spark.sql(f"""
SELECT canonical_label, signal_type, relevance_direction, primary_place_name,
       event_date_min, event_date_max, signal_count, document_count, source_count
FROM {catalog}.{schema}.silver_events
WHERE signal_count > 1 ORDER BY signal_count DESC
"""))

# COMMAND ----------
# MAGIC %md ## Comments on silver_events (for Genie / discoverability)

# COMMAND ----------

_EVENT_TABLE_COMMENT = ("Distinct real-world events: near-duplicate signals describing the same event "
                        "(same type/direction/place/date) are collapsed here, turning duplicate scraping "
                        "into a corroboration count. One row per event; members stay in silver_signals via event_id.")
_EVENT_COL_COMMENTS = {
    "event_id": "Stable event id (evt_<hash> of signal_type|relevance_direction|primary_place_geoid|event_date).",
    "canonical_label": "Short human-readable label for the event.",
    "signal_type": "Signal type shared by the event members (see silver_signals.signal_type).",
    "relevance_direction": "opportunity, risk, or watch.",
    "primary_place_geoid": "FIPS geoid of the event place, or state:<X> when no place resolved.",
    "primary_place_name": "Canonical name of the event place.",
    "event_date_min": "Earliest member event date.",
    "event_date_max": "Latest member event date.",
    "signal_count": "Number of member signals — corroboration strength.",
    "document_count": "Distinct source documents across members.",
    "source_count": "Distinct sources across members — cross-source corroboration.",
    "confidence": "Max member overall_confidence.",
    "match_method": "How canonical_label was assigned.",
    "match_confidence": "Confidence of the label assignment (0-1).",
    "rep_signal_id": "Representative member signal (highest confidence).",
    "rep_summary": "Representative member summary.",
    "rep_why_go": "Representative why-it-matters.",
    "rep_url": "Representative source URL.",
}
_q = "'"
spark.sql(f"COMMENT ON TABLE {catalog}.{schema}.silver_events IS '{_EVENT_TABLE_COMMENT.replace(_q, _q + _q)}'")
for _c, _cm in _EVENT_COL_COMMENTS.items():
    spark.sql(f"ALTER TABLE {catalog}.{schema}.silver_events ALTER COLUMN {_c} COMMENT '{_cm.replace(_q, _q + _q)}'")
print("comments applied to silver_events")

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
