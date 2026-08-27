# Databricks notebook source
# MAGIC %md
# MAGIC # Silver 05 (prototype) — LLM batch canonicalization of orgs & policies
# MAGIC
# MAGIC **Prototype, not yet wired into `silver_job.yml`.** Runs *alongside* the deterministic
# MAGIC resolver in stage 04 so we can compare, not replace it.
# MAGIC
# MAGIC The idea (see the design discussion): the LLM is strong at the **judgment** —
# MAGIC deciding which surface strings name the same real-world entity — where the regex/alias
# MAGIC rules in `go_opps.resolution` give out. We keep the part it must never own — the
# MAGIC **canonical id** — deterministic: each cluster's id is a stable hash of its canonical
# MAGIC name, assigned by us.
# MAGIC
# MAGIC Flow: distinct org/policy surfaces (a small set) → **one `ai_query` per kind** that
# MAGIC clusters them → deterministic ids per cluster (no surface ever dropped). Writes
# MAGIC `silver_<kind>_llm` + `silver_<kind>_llm_map` and prints a comparison vs. the
# MAGIC deterministic `silver_organizations` / `silver_policies`.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
dbutils.widgets.text("model", "")
dbutils.widgets.text("confidence_threshold", "")
# Safety valve for a single-call batch. If the distinct set is larger, we still
# send it (models handle a few hundred), but warn — batching is the productionization step.
dbutils.widgets.text("max_surfaces", "400")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
max_surfaces = int(dbutils.widgets.get("max_surfaces"))

import json

from go_opps.canonicalize import (
    DEFAULT_CANON_MODEL,
    assign_ids,
    build_instruction,
    build_payload,
    response_format_json,
)
from go_opps.extraction import DEFAULT_CONFIDENCE_THRESHOLD

model = dbutils.widgets.get("model") or DEFAULT_CANON_MODEL
threshold = float(dbutils.widgets.get("confidence_threshold") or DEFAULT_CONFIDENCE_THRESHOLD)
print(f"model={model}, confidence_threshold={threshold}")

# COMMAND ----------
# MAGIC %md ## Source — distinct org/policy surfaces from relevant extractions
# MAGIC We canonicalize the surfaces from GO-relevant, above-threshold extractions (the same
# MAGIC set that feeds the curated signals), so the prototype is comparable to stage 04.

# COMMAND ----------

# Minimal projection of the extraction response — just the two NER arrays + the
# fields we filter on. from_json needs a constant schema.
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW _canon_src AS
WITH parsed AS (
  SELECT from_json(
    response,
    'struct<is_go_relevant:boolean, confidence:double, organizations:array<string>, policies:array<string>>'
  ) AS s
  FROM {catalog}.{schema}.silver_signal_extractions
  WHERE response IS NOT NULL
)
SELECT s.organizations, s.policies
FROM parsed
WHERE s.is_go_relevant = true AND s.confidence >= {threshold}
""")

print("relevant extractions:", spark.table("_canon_src").count())

# COMMAND ----------
# MAGIC %md ## Run one clustering batch per kind, assign deterministic ids

# COMMAND ----------


def distinct_surfaces(kind: str) -> list[tuple[int, str, int]]:
    """(id, surface, doc_count) for the distinct surfaces of a NER field, id by frequency."""
    rows = spark.sql(f"""
        SELECT trim(name) AS surface, count(*) AS n
        FROM _canon_src LATERAL VIEW explode({kind}) t AS name
        WHERE length(trim(name)) > 0
        GROUP BY trim(name)
        ORDER BY n DESC, surface
    """).collect()
    return [(i, r["surface"], r["n"]) for i, r in enumerate(rows)]


def cluster(kind: str, items: list[tuple[int, str, int]]) -> list[dict]:
    """One ai_query batch → the model's clusters (raise on API/parse error)."""
    if len(items) > max_surfaces:
        print(f"  ⚠️  {len(items)} surfaces > max_surfaces={max_surfaces}; sending anyway "
              f"(productionize with batching + cross-batch merge).")
    # Endpoint is inlined as a literal (as in stage 03); the long instruction, the
    # payload, and the response schema pass as parameter markers.
    resp = spark.sql(
        f"""
        SELECT ai_query(
          '{model}',
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
        raise RuntimeError(f"ai_query failed for {kind}: {resp['errorMessage']}")
    return json.loads(resp["result"])["clusters"]


def run_kind(kind: str) -> None:
    items = distinct_surfaces(kind)
    print(f"\n=== {kind}: {len(items)} distinct surfaces ===")
    if not items:
        print("  (nothing to canonicalize)")
        return

    dims, maps = assign_ids(cluster(kind, items), items, kind)

    spark.createDataFrame(
        dims,
        "id string, canonical_name string, entity_type string, match_method string, match_confidence double",
    ).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        f"{catalog}.{schema}.silver_{kind}_llm"
    )
    spark.createDataFrame(maps, "surface string, id string") \
        .write.mode("overwrite").option("overwriteSchema", "true") \
        .saveAsTable(f"{catalog}.{schema}.silver_{kind}_llm_map")

    print(f"  {len(items)} surfaces -> {len(dims)} canonical entities "
          f"(-{len(items) - len(dims)} merged)")


run_kind("organizations")
run_kind("policies")

# COMMAND ----------
# MAGIC %md ## Compare — deterministic (stage 04) vs. LLM canonicalization
# MAGIC Fewer canonical entities from the same surfaces = more variants merged. The merge
# MAGIC examples below are what the deterministic rules miss.

# COMMAND ----------


def compare(kind: str, det_table: str) -> None:
    llm_n = spark.table(f"{catalog}.{schema}.silver_{kind}_llm").count()
    surf_n = spark.table(f"{catalog}.{schema}.silver_{kind}_llm_map").count()
    try:
        det_n = spark.table(f"{catalog}.{schema}.{det_table}").count()
        det_str = str(det_n)
    except Exception:
        det_str = "n/a (stage 04 not run)"
    print(f"{kind}: {surf_n} surfaces | deterministic={det_str} entities | llm={llm_n} entities")


compare("organizations", "silver_organizations")
compare("policies", "silver_policies")

# COMMAND ----------
# MAGIC %md ### Organizations the LLM merged (multi-surface clusters)

# COMMAND ----------

display(spark.sql(f"""
SELECT d.canonical_name, d.entity_type, d.match_confidence,
       array_sort(collect_set(m.surface)) AS surfaces, count(*) AS n_surfaces
FROM {catalog}.{schema}.silver_organizations_llm d
JOIN {catalog}.{schema}.silver_organizations_llm_map m ON m.id = d.id
GROUP BY d.canonical_name, d.entity_type, d.match_confidence
HAVING count(*) > 1
ORDER BY n_surfaces DESC, d.canonical_name
LIMIT 30
"""))

# COMMAND ----------
# MAGIC %md ### Policies the LLM merged (multi-surface clusters)

# COMMAND ----------

display(spark.sql(f"""
SELECT d.canonical_name, d.entity_type, d.match_confidence,
       array_sort(collect_set(m.surface)) AS surfaces, count(*) AS n_surfaces
FROM {catalog}.{schema}.silver_policies_llm d
JOIN {catalog}.{schema}.silver_policies_llm_map m ON m.id = d.id
GROUP BY d.canonical_name, d.entity_type, d.match_confidence
HAVING count(*) > 1
ORDER BY n_surfaces DESC, d.canonical_name
LIMIT 30
"""))

# COMMAND ----------
# MAGIC %md ### Anything the model dropped (fell back to a per-surface id)

# COMMAND ----------

display(spark.sql(f"""
SELECT 'organizations' AS kind, canonical_name FROM {catalog}.{schema}.silver_organizations_llm
WHERE match_method = 'llm_unassigned'
UNION ALL
SELECT 'policies' AS kind, canonical_name FROM {catalog}.{schema}.silver_policies_llm
WHERE match_method = 'llm_unassigned'
"""))
