# Databricks notebook source
# MAGIC %md
# MAGIC # Silver eval — extraction quality (entity_grounding · completeness · GO-relevance)
# MAGIC Quality of the silver-layer entity extraction, judged by three LLM judges:
# MAGIC - **entity_grounding** — is every extracted entity (place, org, policy, population, date) +
# MAGIC   quote both present in the source AND meaningful to the signal? (nothing invented / incidental)
# MAGIC - **completeness** (ratio) — of the output signature's source-dependent fields, what
# MAGIC   fraction the source supports were actually captured?
# MAGIC - **go_relevance** — is the kept signal genuinely on GO's mission?
# MAGIC
# MAGIC AI Functions (`ai_query`) emit no MLflow traces, so we can't trace the pipeline live.
# MAGIC Instead we build a static "answer sheet" from the tables the pipeline already produced —
# MAGIC each kept signal joined back to the **exact chunk the extractor saw** and its **raw
# MAGIC extracted entities** — and score it via **`mlflow.genai.evaluate`**. Reference-free —
# MAGIC no labels needed. Runs off the critical path.

# COMMAND ----------
# MAGIC %pip install -U "mlflow[databricks]>=3.1" databricks-agents
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
# Strong judge for a reasoning task; swappable. Same endpoint the canon/event stages use.
dbutils.widgets.text("judge_model", "databricks-claude-sonnet-4-5")
# Keep it cheap: score a small random sample. 0 = score every signal.
dbutils.widgets.text("sample_size", "40")
# Experiment lives directly under /Shared (which exists) — MLflow does not create
# nested parent directories, so a deeper path would fail unless pre-created.
dbutils.widgets.text("experiment", "/Shared/silver-eval")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
judge_model = dbutils.widgets.get("judge_model")
sample_size = int(dbutils.widgets.get("sample_size"))
experiment = dbutils.widgets.get("experiment")
print(f"extraction-quality eval — judge={judge_model}, sample={sample_size or 'ALL'}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Build the answer sheet
# MAGIC Join each curated signal to the chunk the extractor actually read (`silver_signals`
# MAGIC carries the winning `chunk_id`). That chunk text is the "source document" the judge
# MAGIC checks the output against.

# COMMAND ----------

from pyspark.sql import functions as F

# We evaluate the RAW extraction (silver_signal_extractions.response), not the resolved
# dimensions: the raw output holds the entity SURFACES the model pulled from the chunk and
# the model's own event_date (empty when the source states none) — both groundable against
# the chunk. The resolved dims instead hold canonicalized names ("...(DHCS)") that won't
# appear verbatim in the text. We join each KEPT signal to its winning chunk's extraction.
_EXTRACTION_DDL = (
    "struct<signal_type:string, relevance_direction:string, issue_labels:array<string>, "
    "summary:string, affected_populations:array<string>, "
    "places:array<struct<name:string, level:string, state:string>>, "
    "organizations:array<string>, policies:array<string>, event_date:string, "
    "supporting_quote:string, why_go:string>"
)

signals = spark.sql(f"""
  WITH ex AS (
    SELECT chunk_id, from_json(response, '{_EXTRACTION_DDL}') AS s
    FROM {catalog}.{schema}.silver_signal_extractions
    WHERE response IS NOT NULL
  )
  SELECT
    s.signal_id, s.signal_type, s.relevance_direction, s.confidence,
    d.source, d.title,
    ck.text                                                        AS chunk_text,  -- model input
    ex.s.summary                                                   AS summary,
    ex.s.why_go                                                    AS why_go,
    ex.s.supporting_quote                                          AS quote,
    ex.s.event_date                                                AS event_date,   -- raw model date
    -- extracted entity SURFACES, flattened to string arrays for the judge
    transform(ex.s.places, x -> trim(concat(x.name,
        CASE WHEN coalesce(x.state,'') <> '' THEN concat(' [', x.state, ']') ELSE '' END)))
                                                                   AS places,
    ex.s.organizations                                             AS organizations,
    ex.s.policies                                                  AS policies,
    ex.s.affected_populations                                      AS affected_populations,
    ex.s.issue_labels                                              AS issue_labels
  FROM {catalog}.{schema}.silver_signals s
  JOIN ex                                        ON ex.chunk_id = s.chunk_id
  JOIN {catalog}.{schema}.silver_chunks    ck    ON ck.chunk_id = s.chunk_id
  JOIN {catalog}.{schema}.silver_documents d     USING (document_id)
""")

if sample_size > 0:
    signals = signals.orderBy(F.rand(42)).limit(sample_size)

sample = signals.toPandas()   # small sample -> pandas is the safe input for evaluate
print(f"scoring {len(sample)} signals")
display(sample.head(5))


def _as_list(v):
    """Spark array column -> plain Python list (None-safe) for the judge payload."""
    return list(v) if v is not None else []

# COMMAND ----------
# MAGIC %md
# MAGIC ## The judges — entity grounding · completeness · GO-relevance
# MAGIC `{{ inputs }}` renders the SOURCE chunk; `{{ outputs }}` renders the extracted signal
# MAGIC (entities + generated text). No labels — the source *is* the answer key.
# MAGIC
# MAGIC - **entity_grounding** (`make_judge`) — is every extracted entity (place, org, policy,
# MAGIC   affected population, date) + quote both **present in the source** AND **meaningful to
# MAGIC   the signal** (not an incidental / off-topic mention)? Plus: summary/why_go add nothing
# MAGIC   the source doesn't support.
# MAGIC - **completeness** (`make_judge`, **ratio**) — of the extraction signature's
# MAGIC   source-dependent fields, what fraction the source supports were actually captured
# MAGIC   (reference-free; anchored to the real `response_schema`, not ground truth).
# MAGIC - **go_relevance** (`Guidelines`) — is the kept signal genuinely on GO's mission? This
# MAGIC   measures the *precision* of the extractor's relevance gate.

# COMMAND ----------

import mlflow
from mlflow.genai.judges import make_judge
from mlflow.genai.scorers import Guidelines

entity_grounding = make_judge(
    name="entity_grounding",
    model=f"databricks:/{judge_model}",
    feedback_value_type=bool,
    instructions="""
You are checking whether the ENTITIES an extractor pulled from a source are grounded in it
AND meaningful to the signal. The Global Orphan (GO) Project serves vulnerable US children
and families via its CarePortal platform. Use ONLY the SOURCE — no outside knowledge.

SOURCE:
{{ inputs }}

EXTRACTED SIGNAL (entities + generated text):
{{ outputs }}

Judge the extracted entities — outputs.places, outputs.organizations, outputs.policies,
outputs.affected_populations, outputs.event_date, and outputs.quote. For EACH populated
item BOTH conditions must hold:
  (a) GROUNDED — it is explicitly stated in, or directly and unambiguously supported by,
      the SOURCE. Obvious abbreviations/variants of a name that IS in the source are fine;
      an event_date must be a date stated in the SOURCE; the quote must be text taken from
      the SOURCE.
  (b) MEANINGFUL — it is genuinely pertinent to THIS GO-relevant signal, not an incidental
      or off-topic mention scraped from the page (e.g. a navigation label, an unrelated
      organization named only in passing, or a place that is not where the development
      actually occurs).
Empty lists / fields are fine — do not penalize them.

Also require that outputs.summary and outputs.why_go introduce no specific fact — a date,
place, organization, policy, number, affected population, or causal impact — that the
SOURCE does not support.

Return true only if EVERY populated entity is both grounded and meaningful AND summary/why_go
add nothing unsupported. Otherwise return false and name the failing entity, stating whether
it is a grounding problem or a meaningfulness problem.
""",
)

# The completeness judge is anchored to the REAL extraction output signature (the schema in
# go_opps.extraction), so its field set can't drift from what the pipeline actually produces.
from go_opps.extraction import response_schema

_SIGNATURE = "\n".join(
    f"- {name}: {(spec.get('description') or '').strip()}".rstrip(": ")
    for name, spec in response_schema()["properties"].items()
)
# Fields whose presence depends on what the SOURCE contains (the coverage set).
_COVERAGE_FIELDS = "event_date, places, organizations, policies, affected_populations, issue_labels"

completeness = make_judge(
    name="completeness",
    model=f"databricks:/{judge_model}",
    feedback_value_type=float,
    instructions=(
        "You are measuring how COMPLETELY the extractor filled its structured output "
        "signature from the source — a field-coverage RATIO, judged ONLY against the SOURCE "
        "(no outside knowledge, no ground-truth answer key).\n\n"
        "REQUIRED OUTPUT SIGNATURE (the fields the extractor is contracted to produce):\n"
        + _SIGNATURE + "\n\n"
        "SOURCE:\n{{ inputs }}\n\n"
        "EXTRACTED SIGNAL:\n{{ outputs }}\n\n"
        "Score coverage over exactly these source-dependent fields of the signature:\n  "
        + _COVERAGE_FIELDS + "\n\n"
        "For EACH of those fields decide, from the SOURCE alone:\n"
        "  - APPLICABLE — the SOURCE actually provides this information (states a date; names "
        "a place, organization, or bill/policy; identifies an affected population; or clearly "
        "concerns a GO issue category). A field the SOURCE says nothing about is NOT applicable "
        "and must not count against the score.\n"
        "  - Among APPLICABLE fields, CAPTURED — the extraction populated it with a non-empty "
        "value that reflects the SOURCE.\n\n"
        "Return the ratio CAPTURED / APPLICABLE as a decimal between 0 and 1 (return 1.0 if no "
        "field is applicable). In the rationale, list each applicable field and whether it was "
        "captured or missed, with the counts you used."
    ),
)

# GO-relevance: a Guidelines judge over the source + signal. Measures whether the kept
# signal is genuinely on-mission (the precision of the extractor's is_go_relevant gate).
go_relevance = Guidelines(
    name="go_relevance",
    model=f"databricks:/{judge_model}",
    guidelines=[
        "Using the source text in inputs.chunk_text as the only evidence, the extracted "
        "signal is relevant to the Global Orphan (GO) Project only if the source establishes "
        "a clear connection to vulnerable US children and families: children or adolescents; "
        "parents, caregivers, or families; foster care, kinship care, adoption, reunification, "
        "or child welfare; housing stability or homelessness; food or material needs; "
        "healthcare access; youth mental health; education access or school support; poverty, "
        "income support, childcare cost, or family economic stability; or emergencies and "
        "disasters affecting children or families. It PASSES only if the source supports such "
        "a connection. Generic business, sports, elections, or adult-only content with no "
        "clear link to children or families FAILS.",
    ],
)

# Pack columns into the inputs / outputs shape the judges read. outputs carries the raw
# extracted entities (surfaces the model pulled from the chunk) plus the generated text.
data = [
    {
        "inputs": {"signal_id": r.signal_id, "chunk_text": r.chunk_text,
                   "source": r.source, "title": r.title},
        "outputs": {
            "summary": r.summary,
            "why_go": r.why_go,
            "quote": r.quote,
            "signal_type": r.signal_type,
            "relevance_direction": r.relevance_direction,
            "event_date": r.event_date,
            "places": _as_list(r.places),
            "organizations": _as_list(r.organizations),
            "policies": _as_list(r.policies),
            "affected_populations": _as_list(r.affected_populations),
            "issue_labels": _as_list(r.issue_labels),
        },
    }
    for r in sample.itertuples()
]

# COMMAND ----------
# MAGIC %md
# MAGIC ## Score the dataset with `mlflow.genai.evaluate`
# MAGIC One call applies both judges to every row (answer-sheet mode — pre-computed
# MAGIC `outputs`, no `predict_fn`). MLflow creates the run, calls the judges **in parallel**,
# MAGIC and records per-row pass/fail + rationales as trace assessments plus aggregate metrics
# MAGIC (`entity_grounding/mean`, `completeness/mean`) — no manual run/metric bookkeeping.

# COMMAND ----------

mlflow.set_experiment(experiment)

result = mlflow.genai.evaluate(
    data=data,
    scorers=[entity_grounding, completeness, go_relevance],
)
print("aggregate metrics:", result.metrics)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Per-row results — each judge's bool + rationale
# MAGIC `evaluate` records the full detail as trace assessments (visible in the run's
# MAGIC **Evaluations** tab). Here we flatten them to a tidy table — one row per signal, each
# MAGIC judge's pass/fail **and its rationale** — for display and SQL inspection
# MAGIC (`silver_eval_results`). Non-fatal: the metrics are already logged by `evaluate`.

# COMMAND ----------

import json

import pandas as pd

_JUDGES = ["entity_grounding", "completeness", "go_relevance"]


def _assessment(asmts, name, want):
    """Pull one judge's value or rationale from a trace's assessments (obj or dict)."""
    for a in asmts if asmts is not None else []:
        nm = getattr(a, "name", None) or (a.get("assessment_name") if isinstance(a, dict) else None)
        if nm != name:
            continue
        if want == "rationale":
            return getattr(a, "rationale", None) or (a.get("rationale") if isinstance(a, dict) else None)
        fb = getattr(a, "feedback", None)
        if fb is not None:
            return getattr(fb, "value", None)
        if isinstance(a, dict):
            return (a.get("feedback") or {}).get("value")
        return getattr(a, "value", None)


def _short(x):
    try:
        return json.dumps(x, default=str)[:1500]
    except Exception:
        return str(x)[:1500]


try:
    traces = mlflow.search_traces(run_id=result.run_id)
    rows = []
    for _, t in traces.iterrows():
        a = t.get("assessments")
        rec = {"trace_id": str(t.get("trace_id") or t.get("request_id") or "")}
        for j in _JUDGES:
            rec[j] = _assessment(a, j, "value")
            rec[f"{j}_rationale"] = _assessment(a, j, "rationale")
        rec["request"] = _short(t.get("request"))
        rec["response"] = _short(t.get("response"))
        rows.append(rec)

    flat = pd.DataFrame(rows)
    display(flat)

    # Persist for SQL inspection / trending (all-string to sidestep nested-type conversion).
    spark.createDataFrame(flat.astype(str)).write.mode("overwrite") \
        .option("overwriteSchema", "true").saveAsTable(f"{catalog}.{schema}.silver_eval_results")
    print(f"wrote {len(flat)} rows to {catalog}.{schema}.silver_eval_results")
except Exception as e:  # never fail the job on the inspection step — metrics are already logged
    print("per-row flattening skipped:", repr(e))
