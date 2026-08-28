# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — knowledge graph nodes + edges
# MAGIC A **derived projection** of the silver star into a uniform `{nodes, edges}` shape for
# MAGIC the graph view / interactive explorer (solution-design §5 🟦, §8 `Could`). This is a
# MAGIC pure SQL denormalization — **never a system of record**: the star schema stays
# MAGIC authoritative, and a full reprocess (`CREATE OR REPLACE`) rebuilds both tables.
# MAGIC
# MAGIC - **Nodes**: signals + every entity type (issue, place, organization, policy).
# MAGIC - **Edges**: signal→issue (`CONCERNS`), signal→place (`AFFECTS`),
# MAGIC   signal→org (`INVOLVES`), signal→policy (`REFERENCES`) from the bridges, plus derived
# MAGIC   **issue↔place co-occurrence** (`CO_OCCURS`) computed from signals that share both.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
print(f"Building graph in {catalog}.{schema}")

# COMMAND ----------
# MAGIC %md ## Edges
# MAGIC Union the bridge tables (one directed edge per link, carrying confidence + evidence),
# MAGIC plus derived issue↔place co-occurrence edges. `edge_id` is a deterministic hash of
# MAGIC `(src, predicate, dst)` so a later switch to incremental `MERGE` is a drop-in change.

# COMMAND ----------

# Node ids are type-prefixed so they're globally unique across the union.
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _edges AS
-- SIGNAL —CONCERNS→ ISSUE
SELECT concat('sig_', si.signal_id) AS src_id, 'signal' AS src_type,
       concat('iss_', si.issue_id)  AS dst_id, 'issue'  AS dst_type,
       'CONCERNS' AS predicate, si.confidence AS confidence,
       si.confidence AS weight, si.evidence_chunk_id AS evidence_chunk_id
FROM {catalog}.{schema}.silver_signal_issues si

UNION ALL
-- SIGNAL —AFFECTS→ PLACE
SELECT concat('sig_', sp.signal_id), 'signal',
       concat('plc_', sp.place_id),  'place',
       'AFFECTS', sp.confidence, sp.confidence, sp.evidence_chunk_id
FROM {catalog}.{schema}.silver_signal_places sp

UNION ALL
-- SIGNAL —INVOLVES→ ORGANIZATION  (Could-have; empty union if no orgs extracted)
SELECT concat('sig_', so.signal_id), 'signal',
       concat('org_', so.org_id),    'organization',
       'INVOLVES', so.confidence, so.confidence, so.evidence_chunk_id
FROM {catalog}.{schema}.silver_signal_orgs so

UNION ALL
-- SIGNAL —REFERENCES→ POLICY
SELECT concat('sig_', spol.signal_id), 'signal',
       concat('pol_', spol.policy_id), 'policy',
       'REFERENCES', spol.confidence, spol.confidence, spol.evidence_chunk_id
FROM {catalog}.{schema}.silver_signal_policies spol

UNION ALL
-- ISSUE —CO_OCCURS→ PLACE  (derived: signals sharing both an issue and a place)
-- weight = # of distinct signals corroborating that (issue, place) pairing.
SELECT concat('iss_', si.issue_id) AS src_id, 'issue' AS src_type,
       concat('plc_', sp.place_id) AS dst_id, 'place' AS dst_type,
       'CO_OCCURS' AS predicate,
       CAST(NULL AS double) AS confidence,
       CAST(count(DISTINCT si.signal_id) AS double) AS weight,
       CAST(NULL AS string) AS evidence_chunk_id
FROM {catalog}.{schema}.silver_signal_issues si
JOIN {catalog}.{schema}.silver_signal_places sp ON sp.signal_id = si.signal_id
GROUP BY si.issue_id, sp.place_id
""")

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.gold_graph_edges AS
SELECT
  md5(concat_ws('|', src_id, predicate, dst_id)) AS edge_id,
  src_id, src_type, dst_id, dst_type, predicate,
  round(weight, 4)     AS weight,
  round(confidence, 4) AS confidence,
  evidence_chunk_id,
  current_timestamp()  AS updated_at
FROM _edges
""")

# COMMAND ----------
# MAGIC %md ## Nodes
# MAGIC Union signals + every entity type into one shape. `degree` (edge count touching the
# MAGIC node) is joined from the edges above so the UI can size nodes by connectivity.

# COMMAND ----------

# degree = how many edges touch each node (as src or dst)
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _degree AS
SELECT node_id, count(*) AS degree FROM (
  SELECT src_id AS node_id FROM {catalog}.{schema}.gold_graph_edges
  UNION ALL
  SELECT dst_id AS node_id FROM {catalog}.{schema}.gold_graph_edges
) GROUP BY node_id
""")

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _nodes AS
-- SIGNAL nodes
SELECT concat('sig_', s.signal_id) AS node_id, 'signal' AS node_type,
       coalesce(nullif(trim(s.summary), ''), s.signal_id) AS label,
       s.signal_type AS subtype, s.relevance_direction AS relevance_direction,
       s.state AS state, s.confidence AS confidence
FROM {catalog}.{schema}.silver_signals s

UNION ALL
-- ISSUE nodes
SELECT concat('iss_', i.issue_id), 'issue', i.label,
       CAST(NULL AS string), CAST(NULL AS string), CAST(NULL AS string), CAST(NULL AS double)
FROM {catalog}.{schema}.silver_issues i

UNION ALL
-- PLACE nodes
SELECT concat('plc_', p.place_id), 'place', p.canonical_name,
       p.level, CAST(NULL AS string), p.state, CAST(NULL AS double)
FROM {catalog}.{schema}.silver_places p

UNION ALL
-- ORGANIZATION nodes (Could-have)
SELECT concat('org_', o.org_id), 'organization', o.canonical_name,
       o.entity_type, CAST(NULL AS string), CAST(NULL AS string), CAST(NULL AS double)
FROM {catalog}.{schema}.silver_organizations o

UNION ALL
-- POLICY nodes (Could-have)
SELECT concat('pol_', pol.policy_id), 'policy', pol.canonical_name,
       pol.entity_type, CAST(NULL AS string), CAST(NULL AS string), CAST(NULL AS double)
FROM {catalog}.{schema}.silver_policies pol
""")

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.gold_graph_nodes AS
SELECT
  n.node_id, n.node_type, n.label, n.subtype, n.relevance_direction,
  n.state, round(n.confidence, 4) AS confidence,
  coalesce(d.degree, 0) AS degree,
  current_timestamp()   AS updated_at
FROM _nodes n
LEFT JOIN _degree d ON d.node_id = n.node_id
""")

# COMMAND ----------
# MAGIC %md ## Validate

# COMMAND ----------

for t in ["gold_graph_nodes", "gold_graph_edges"]:
    print(f"{t}: {spark.table(f'{catalog}.{schema}.{t}').count()}")

print("\nNodes by type:")
display(spark.sql(f"""
SELECT node_type, count(*) AS n, round(avg(degree), 1) AS avg_degree, max(degree) AS max_degree
FROM {catalog}.{schema}.gold_graph_nodes GROUP BY node_type ORDER BY n DESC
"""))

print("Edges by predicate:")
display(spark.sql(f"""
SELECT predicate, count(*) AS n, round(avg(weight), 2) AS avg_weight
FROM {catalog}.{schema}.gold_graph_edges GROUP BY predicate ORDER BY n DESC
"""))
