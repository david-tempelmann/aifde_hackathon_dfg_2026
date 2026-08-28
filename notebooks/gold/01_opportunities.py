# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — opportunity cards, details, citations (+ dims)
# MAGIC Denormalize the silver star into the **serving schema** the app/Lakebase read
# MAGIC (`databricks_postgres.gold.*` in the `go-outreach` Lakebase project). One opportunity
# MAGIC per signal, with a **transparent priority score** whose components are all stored.
# MAGIC
# MAGIC Column names/types match the Lakebase contract exactly so these Delta tables can sync
# MAGIC (reverse ETL) into Lakebase. Full reprocess: `CREATE OR REPLACE`.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
print(f"Building gold in {catalog}.{schema}")

# COMMAND ----------
# MAGIC %md ## Dimensions (mirror the silver dims, projected to the Lakebase columns)

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.gold_dim_issues AS
SELECT issue_id, label, description FROM {catalog}.{schema}.silver_issues
""")
spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.gold_dim_places AS
SELECT place_id, canonical_name, state, level, lat, lon FROM {catalog}.{schema}.silver_places
""")

# COMMAND ----------
# MAGIC %md ## Primary place / issue per signal
# MAGIC A card shows one place and one issue. Pick deterministically: the **finest** place
# MAGIC (place<county<state<nation, then lowest id) and the **highest-confidence** issue.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _primary_place AS
SELECT signal_id, place_id, canonical_name, level FROM (
  SELECT sp.signal_id, sp.place_id, p.canonical_name, p.level,
         row_number() OVER (PARTITION BY sp.signal_id ORDER BY
           CASE p.level WHEN 'place' THEN 1 WHEN 'county' THEN 2 WHEN 'state' THEN 3
                        WHEN 'nation' THEN 4 ELSE 5 END, p.place_id) rn
  FROM {catalog}.{schema}.silver_signal_places sp
  JOIN {catalog}.{schema}.silver_places p USING (place_id)
) WHERE rn = 1
""")
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _primary_issue AS
SELECT signal_id, issue_id, label FROM (
  SELECT si.signal_id, si.issue_id, i.label,
         row_number() OVER (PARTITION BY si.signal_id ORDER BY si.confidence DESC, i.issue_id) rn
  FROM {catalog}.{schema}.silver_signal_issues si
  JOIN {catalog}.{schema}.silver_issues i USING (issue_id)
) WHERE rn = 1
""")

# COMMAND ----------
# MAGIC %md ## Ranking — transparent priority score
# MAGIC `priority = 0.35·impact + 0.25·timing + 0.15·locality + 0.25·evidence`. Every component
# MAGIC is stored on `opportunity_details` so the UI can show *why* a card ranks where it does.
# MAGIC `impact_magnitude` captures **both directions** — a serious risk to CarePortal ranks as
# MAGIC high as a strong opportunity; `watch` is damped.

# COMMAND ----------

# scoring expressions reused across cards + details
_IMPACT = """
  ( CASE signal_type
      WHEN 'proposed_mandate' THEN 1.00 WHEN 'bill_introduced' THEN 0.90
      WHEN 'vote' THEN 0.90 WHEN 'amendment' THEN 0.80 WHEN 'committee_hearing' THEN 0.80
      WHEN 'funding' THEN 0.85 WHEN 'program' THEN 0.70 WHEN 'emergency' THEN 0.70
      WHEN 'report_indicator' THEN 0.60 ELSE 0.50 END )
  * ( CASE relevance_direction WHEN 'risk' THEN 1.00 WHEN 'opportunity' THEN 0.95 ELSE 0.50 END )
"""
# near-term (past or future) events are more urgent; ~90-day linear decay
_TIMING = "greatest(0.0, 1.0 - least(abs(datediff(current_date(), event_date)), 90) / 90.0)"
# finer/in-territory geography is more actionable
_LOCALITY = """
  CASE coalesce(pp.level, 'unresolved')
       WHEN 'place' THEN 1.00 WHEN 'county' THEN 0.85 WHEN 'state' THEN 0.60
       WHEN 'nation' THEN 0.30 ELSE 0.40 END
"""

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _scored AS
SELECT
  s.signal_id, s.document_id, s.signal_type, s.relevance_direction, s.state,
  s.event_date, s.confidence, s.summary, s.why_go, s.affected_populations,
  s.source, s.source_type, s.url, s.quote, s.quote_char_start, s.quote_char_end,
  d.title AS doc_title, d.first_seen_at,
  pp.place_id, pp.canonical_name AS place_name, coalesce(pp.level, 'unresolved') AS place_level,
  pi.issue_id, pi.label AS issue_label,
  round({_IMPACT}, 4)                                          AS impact_magnitude,
  round({_TIMING}, 4)                                          AS timing_urgency,
  round({_LOCALITY}, 4)                                        AS locality,
  round(s.confidence, 4)                                       AS evidence_confidence
FROM {catalog}.{schema}.silver_signals s
LEFT JOIN {catalog}.{schema}.silver_documents d ON d.document_id = s.document_id
LEFT JOIN _primary_place pp ON pp.signal_id = s.signal_id
LEFT JOIN _primary_issue pi ON pi.signal_id = s.signal_id
""")

# COMMAND ----------
# MAGIC %md ## opportunity_cards / _details / _citations

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.gold_opportunity_cards AS
SELECT
  signal_id                                                    AS opportunity_id,
  coalesce(nullif(trim(doc_title), ''), left(summary, 120))    AS title,
  state,
  place_id,
  place_name,
  issue_id,
  issue_label,
  relevance_direction,
  signal_type,
  event_date,
  confidence,
  round(0.35*impact_magnitude + 0.25*timing_urgency + 0.15*locality + 0.25*evidence_confidence, 4)
                                                               AS priority_score,
  source                                                       AS source_name,
  current_timestamp()                                          AS updated_at
FROM _scored
""")

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.gold_opportunity_details AS
SELECT
  signal_id                                                    AS opportunity_id,
  summary,
  why_go                                                       AS why_it_matters,
  CASE relevance_direction
    WHEN 'opportunity' THEN 'Reach out to recruit CarePortal partners and build local momentum around this.'
    WHEN 'risk' THEN 'Escalate for strategic assessment; consider advocacy or amended bill language with local partners.'
    ELSE 'Monitor; revisit if it advances or corroborating signals appear.'
  END                                                          AS recommended_action,
  affected_populations,
  source_type,
  impact_magnitude,
  timing_urgency,
  locality,
  evidence_confidence
FROM _scored
""")

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.gold_opportunity_citations AS
SELECT
  concat('cit_', signal_id)                                    AS citation_id,
  signal_id                                                    AS opportunity_id,
  quote,
  source                                                       AS source_name,
  url                                                          AS source_url,
  quote_char_start                                             AS char_start,
  quote_char_end                                               AS char_end,
  first_seen_at                                                AS retrieved_at,
  true                                                         AS is_primary
FROM _scored
WHERE quote IS NOT NULL
""")

# COMMAND ----------

for t in ["gold_dim_issues", "gold_dim_places", "gold_opportunity_cards",
          "gold_opportunity_details", "gold_opportunity_citations"]:
    print(f"{t}: {spark.table(f'{catalog}.{schema}.{t}').count()}")

display(spark.sql(f"""
SELECT title, state, issue_label, relevance_direction, signal_type,
       round(priority_score,3) priority, round(confidence,2) conf
FROM {catalog}.{schema}.gold_opportunity_cards
ORDER BY priority_score DESC LIMIT 15
"""))
