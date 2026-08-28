# Silver layer — robustness review & offline evaluation plan (v0.1)

> Companion to [`solution-design.md`](./solution-design.md). Two parts:
> **A.** a robustness review of the silver pipeline, focused on entity **extraction** and
> **resolution**; **B.** an implementation plan for an **offline evaluation** that uses
> **Databricks LLM judges + `mlflow.genai.evaluate`** on an eval dataset derived from the
> generated silver tables.
>
> AI Functions (`ai_query`) emit **no MLflow traces**, so live tracing isn't an option. The
> answer is exactly what's proposed here: build a **static "answer-sheet" eval dataset** from
> the tables the pipeline already produces and score it with LLM judges. This gives us a
> quality signal *and* a way to tune the robustness levers below (thresholds, model choice,
> prompt changes) against numbers instead of vibes.

---

## Pipeline under review

```
bronze_raw_issues
  → 01_documents   silver_documents          (clean text, full_text, content_hash)
  → 02_chunks      silver_chunks             (char-window chunks, offsets)
  → 03_extract     silver_signal_extractions (1 ai_query/chunk, strict JSON schema — landing)
  → 04_signals     silver_signals + dims/bridges + events
                     signals · issues · places · organizations · policies
                     signal_issues · signal_places · signal_orgs · signal_policies · events
```

The judgment-heavy work — and therefore the robustness risk — lives in **03/04**:
LLM extraction + relevance gate, deterministic place resolution, LLM org/policy
canonicalization, and LLM event clustering.

---

# Part A — Robustness review

Findings are grouped and tagged **[H]/[M]/[L]** by impact. Each has a concrete remediation.
The evaluation in Part B is designed to *measure* the ones marked ⏱ **(eval-informed)**.

## A1. Extraction & the relevance gate

### A1.1 — One signal per chunk, collapsed to one per `(document, signal_type)` **[H]** ⏱
The prompt extracts **exactly one** primary signal per chunk ("pick the single most GO-relevant
one; do NOT combine"), and `04` then dedups to **one signal per `(document_id, signal_type)`**
via `signal_id = sha2(document_id | signal_type)`, keeping the highest `overall_confidence`.

Consequence: a page that legitimately contains several signals of the same type — a
**legislative digest / committee agenda listing five bills** (`bill_introduced` × 5) — yields
**one** signal. The others are silently dropped. This is the single biggest **recall** risk,
and it hits precisely the legislative sources the use case centers on.

- **Fix (short term):** allow multiple signals per chunk (schema → array of signals), and make
  the dedup key incorporate signal identity (e.g. `hash(document_id, signal_type, normalized_claim)`
  or the bill/instrument number when present) instead of collapsing all same-type signals.
- **Fix (cheap mitigation now):** for known list-style sources, chunk on list-item boundaries so
  each bill lands in its own chunk. Doesn't fully solve it (still collapses per type), but helps.
- Measured by the **funnel metric** (B5) — signals-per-document distribution — and the
  extraction recall spot-check (B3).

### A1.2 — Long documents effectively contribute ≤1 signal per type **[M]**
Long docs split into overlapping chunks; each chunk extracts one signal; `04` then collapses
per `(document, signal_type)`. So a long document contributes at most one signal per type
regardless of chunk count. Same root cause as A1.1, same fix.

### A1.3 — Grounding gate is an exact substring match **[H]** ⏱
`04` locates the quote with `instr(full_text, supporting_quote)` and **drops** any signal where
`quote_pos = 0`. `full_text` has had whitespace collapsed (`\s+ → ' '`) in `01`. If the model
reproduces the *original* spacing/newlines, uses curly quotes, an ellipsis, or trims punctuation
differently, the substring won't match and a **valid** signal is discarded.

- This gate is great for **precision** (no ungrounded fact surfaces — the citations `Must`-have)
  but the **recall cost is invisible**: we don't currently know what fraction of relevant signals
  die here vs. at the relevance or confidence gate.
- **Fix:** (a) add a **normalized** fallback match (collapse whitespace + unify quote glyphs on
  both sides before `instr`); (b) as a last resort, fuzzy-locate (longest common substring) and
  record `grounding_method`; (c) emit the **per-gate drop counts** (B5) so the recall cost is
  visible. `instr` also returns the *first* occurrence — fine for citation, worth noting.

### A1.4 — Relevance gate & direction are single-shot, unverified model outputs **[H]** ⏱
`is_go_relevant`, `relevance_direction` (opportunity/risk/watch), `signal_type`, and
`issue_labels` all come from **one** `ai_query` with **no verification pass**. Solution-design §3
envisioned a verification step ("must cite a chunk or it's dropped"); grounding is enforced, but
the *semantic* judgments (is this really GO-relevant? is "risk" the right direction?) are not
checked. False positives (generic civic news let through) and false negatives (a real
child-welfare signal missed) are both invisible today. **This is the #1 eval target** (B2/B3).

### A1.5 — Fixed confidence threshold on a self-reported score **[M]** ⏱
The gate uses `overall_confidence ≥ 0.4`, a single hardcoded threshold on a **self-reported**
LLM confidence. LLM confidence is notoriously miscalibrated, and 0.4 was chosen a priori.
- **Fix:** treat the threshold as a tunable, and **calibrate it against judge/human labels**
  (B2 gives precision/recall as a function of the threshold, so 0.4 becomes an evidence-based
  choice rather than a guess).

### A1.6 — Extraction model is haiku, never A/B'd **[M]** ⏱
`DEFAULT_MODEL = databricks-claude-haiku-4-5`. Reasonable for cheap batch, but haiku is the
weaker instruction-follower for strict verbatim grounding + nuanced relevance. The pipeline is
already model-swappable via the `model` widget → the eval (B) can run the same dataset twice
(haiku vs. sonnet) and quantify the accuracy/cost trade-off.

### A1.7 — JSON parse failures & errored rows silently vanish **[M]**
`03` keeps errored rows (`error_message` populated, `response` null) for observability, and `04`
starts from `WHERE response IS NOT NULL` then `from_json(...)`; an unparseable response yields a
NULL struct → all gate predicates are NULL → the row is filtered out. So both LLM errors and
parse failures disappear with no reconciliation between the `03` error count and the `04` intake.
- **Fix:** surface `error_message IS NOT NULL` count and `from_json = NULL` count in the funnel
  (B5); optionally a bounded retry for errored chunks.

## A2. Entity resolution

### A2.1 — Place resolution only scopes to NY/CA/VA **[M]** ⏱
`terr_states` recognizes only NY/CA/VA (plus literal state names); every other state hint
collapses to NULL, and `scope_usps` for the alias join is therefore only ever `NY/CA/VA` or
NULL. A place in an ambiguous/`OTHER` signal can only resolve through `_alias_unique`
(nationally unique alias). So an ambiguous **"Richmond"** (VA / CA / others — not unique) won't
resolve and lands as `u_<hash>` `unresolved` with no lat/lon (no map pin). Fine for the scoped
territory, a known gap for out-of-territory/ambiguous geography.
- **Fix (later):** widen scoping to all 50 states (the gazetteer already covers them); use the
  signal's `state` even when it's not a territory. Measured by resolution accuracy + `%
  unresolved` (B4/B5).

### A2.2 — Stale docstring in `resolution.py` **[L]**
`normalize_place_name` says *"MUST mirror the SQL in stage 04"*, but `04` now registers the
Python function itself as the `normalize_place` UDF — there is no separate SQL copy to mirror.
Harmless, but update the comment so no one hunts for a phantom SQL block.

### A2.3 — Org/policy canonicalization & event clustering send the whole corpus in one call **[M]**
Both `canonicalize_ner` and event clustering issue **one** `ai_query` over **all** distinct
surfaces / all signals. At hackathon volume this is fine (and cheap). As the corpus grows,
thousands of distinct org strings in one prompt risks context/output truncation → dropped
clusters (which then fall back to `llm_unassigned` singletons, quietly hurting resolution).
- **Fix (later):** batch the canonicalization/clustering input (e.g. blocked by first letter /
  by state) with a merge pass, or cap batch size. Track `% llm_unassigned` and singleton-event
  rate as the early-warning metric (B5).

### A2.4 — A single LLM error aborts the whole `04` stage **[M]**
Extraction uses `failOnError => false`, but `canonicalize_ner` and `_cluster_events` **`raise
RuntimeError`** on any `errorMessage`. One transient canonicalization/clustering error kills the
entire signals stage — inconsistent with the "one bad row shouldn't fail the batch" principle
used in `03`.
- **Fix:** on canonicalization/clustering failure, **fall back to singletons** (every surface its
  own id / every signal its own event) instead of raising. The `assign_*` fallbacks already
  handle "model dropped this id" — extend that to "model call failed entirely" so the pipeline
  degrades gracefully rather than aborting.

### A2.5 — Resolution/clustering quality is entirely unmeasured **[H]** ⏱
Place resolution, org/policy canonicalization, and event clustering all make judgment calls that
directly drive the graph, the corroboration counts, and the map — and none is measured. Wrong
merges (two agencies fused) and missed merges (one entity split across ids) are both invisible.
Primary eval target for Part B (B4).

## A3. Observability (cross-cutting) **[H]**
There is **no funnel** and **no quality metric** today. You cannot answer "of N chunks, how many
became signals, and where did the rest die?" or "how good are the signals we kept?". Every finding
above is hard to prioritize without these two numbers. Part B delivers both: a cheap deterministic
**funnel/quality table** (B5) and the **LLM-judge quality scores** (B2–B4).

---

# Part B — Offline evaluation (LLM judges + `mlflow.genai.evaluate`)

## B0. Approach & why

- **Static "answer-sheet" evaluation.** AI Functions produce no traces, so we build an eval
  DataFrame with `inputs` (what the model saw), `outputs` (what it produced), and optional
  `expectations` (ground truth), then call `mlflow.genai.evaluate(data=..., scorers=[...])`
  **without a `predict_fn`** — MLflow just scores the rows. Confirmed as the current MLflow 3 /
  Databricks recommendation (the older `mlflow.evaluate(model_type="databricks-agent")` is
  superseded; `model_type` is no longer needed).
- **Reference-free first.** Most of what we care about — grounding/faithfulness, relevance-gate
  correctness, direction plausibility — needs **no labels** and can run over the generated tables
  immediately via `Guidelines` and `make_judge()` scorers. A **small human-labeled gold set**
  (~30–50 rows) is added only for `Correctness` and for **calibrating** the judges.
- **Offline / off the critical path.** Ships as its own notebooks + bundle job; run ad hoc.
  Later it can gate the pipeline or run nightly.

## B1. Eval targets (what we score)

| # | Target | Table(s) | Judge type | Needs GT? |
|---|--------|----------|-----------|-----------|
| T1 | **Grounding / faithfulness** — summary & `why_go` fully supported by source; no invented facts | `silver_signals` ⋈ `silver_chunks` | Guidelines (reference-free) | No |
| T2 | **Quote support** — `supporting_quote` is verbatim & actually supports the signal | `silver_signals` ⋈ `silver_documents` | Guidelines + deterministic substring check | No |
| T3 | **Relevance-gate precision** — kept signals really are GO-relevant | `silver_signals` ⋈ chunk | `make_judge` (bool) | No |
| T4 | **Relevance-gate recall** — GO-relevant signals we *dropped* at the gate | dropped rows from `silver_signal_extractions` | `make_judge` (bool) | No |
| T5 | **Direction** — opportunity/risk/watch justified from GO's view | `silver_signals` ⋈ chunk | `make_judge` (categorical) | No |
| T6 | **Classification** — `signal_type` & `issue_labels` appropriate | `silver_signals`, `silver_signal_issues` | `make_judge` (categorical) | No |
| T7 | **Place resolution** — resolved `canonical_name`+`state`+`geoid` correct for the mention | `silver_signal_places` ⋈ `silver_places` | `make_judge` (bool) | No |
| T8 | **Org/policy canonicalization** — all surfaces in a cluster are the same entity; name correct | `silver_organizations`/`silver_policies` (`aliases`) | `make_judge` (bool) | No |
| T9 | **Event clustering** — members describe the same real-world event | `silver_events` + members | `make_judge` (bool) | No |
| T10 | **Correctness** (spot) — extracted signal matches human-labeled facts | gold subset | built-in `Correctness` | **Yes** |
| T11 | **Safety** — no unsafe content in generated summaries/`why_go` | `silver_signals` | built-in `Safety` | No |

T1–T3, T5–T9, T11 run over the current tables with **zero labeling**. T4 (recall) and T10 need a
little setup (dropped-row sampling; a gold set).

## B2. Building the eval datasets (from the generated tables)

The judge must see **the same context the extractor saw** — join a signal back to its winning
chunk (both `silver_signals` and `silver_signal_extractions` carry `chunk_id`).

**Signal-quality dataset** (T1–T3, T5, T6, T11):

```sql
CREATE OR REPLACE TABLE {cat}.{sch}.eval_signal_rows AS
SELECT
  s.signal_id,
  s.signal_type, s.relevance_direction, s.confidence, s.source_type, s.state,
  d.source, d.title,
  ck.text                                   AS chunk_text,   -- what the model saw
  s.summary, s.why_go, s.quote,
  array_join(collect_list(i.label), '; ')   AS issue_labels
FROM {cat}.{sch}.silver_signals s
JOIN {cat}.{sch}.silver_chunks    ck USING (chunk_id)
JOIN {cat}.{sch}.silver_documents d  USING (document_id)
LEFT JOIN {cat}.{sch}.silver_signal_issues si USING (signal_id)
LEFT JOIN {cat}.{sch}.silver_issues        i  ON i.issue_id = si.issue_id
GROUP BY ALL;
```

**Dropped-signal dataset** (T4 — relevance recall). Re-parse the landing table and keep rows the
gate rejected, so judges can find false negatives:

```sql
CREATE OR REPLACE TABLE {cat}.{sch}.eval_dropped_rows AS
WITH p AS (
  SELECT e.chunk_id, e.document_id, from_json(e.response, '<extraction DDL>') AS s
  FROM {cat}.{sch}.silver_signal_extractions e WHERE e.response IS NOT NULL
)
SELECT p.chunk_id, ck.text AS chunk_text, d.source, d.title,
       p.s.is_go_relevant, p.s.overall_confidence, p.s.summary, p.s.supporting_quote
FROM p JOIN {cat}.{sch}.silver_chunks ck USING (chunk_id)
       JOIN {cat}.{sch}.silver_documents d USING (document_id)
WHERE NOT (p.s.is_go_relevant AND p.s.overall_confidence >= 0.4
           AND instr(d.full_text, p.s.supporting_quote) > 0);   -- everything the gate cut
```

**Resolution / clustering datasets** (T7–T9) are small (dimension-sized) — one row per resolved
place, per org/policy cluster (feed `aliases`), and per event (feed member titles/dates/places).

**Sampling & cost.** Judges are LLM calls. For T1–T6/T11, run over a **stratified sample**
(~150–250 rows) spanning `source_type × signal_type × relevance_direction × confidence-band`, so
low-confidence and each direction are represented. Resolution/clustering (T7–T9) are already small
enough to run in full. `mlflow.genai.evaluate` accepts a Spark or pandas DataFrame; sample in SQL.

## B3. Scorers — built-in + custom

`go_opps/eval.py` holds the rubrics/judge builders (versioned with the wheel, same pattern as
`extraction.py`), so prompts live in code and can't drift from the notebook.

```python
# go_opps/eval.py  (sketch)
from mlflow.genai.scorers import Guidelines, Safety, Correctness, RelevanceToQuery
from mlflow.genai.judges import make_judge

JUDGE_MODEL = "databricks:/databricks-claude-sonnet-4-5"   # strong judge; swappable via widget

# --- Reference-free guideline judges (T1, T2) -------------------------------
grounding = Guidelines(
    name="grounding",
    model=JUDGE_MODEL,
    guidelines=[
        "Every factual claim in outputs.summary and outputs.why_go must be supported by "
        "inputs.chunk_text. The response must not introduce dates, places, organizations, "
        "policies, populations, or GO/CarePortal impacts that are not present in the source.",
    ],
)
quote_support = Guidelines(
    name="quote_support",
    model=JUDGE_MODEL,
    guidelines=[
        "outputs.quote must be text taken from inputs.chunk_text and must directly support "
        "outputs.summary and the assigned signal_type. A quote that is off-point or does not "
        "appear in the source fails.",
    ],
)

# --- Custom judges for the gate & classification (T3–T6) --------------------
relevance_gate = make_judge(
    name="go_relevance",
    model=JUDGE_MODEL,
    feedback_value_type=bool,
    instructions="""
Global Orphan (GO) Project serves vulnerable US children and families; its CarePortal platform
connects local partners with concrete needs of children in crisis and families in the
child-welfare/foster-care system.

Source:
{{ inputs }}

Extracted signal:
{{ outputs }}

Return true only if the source plausibly concerns children/adolescents; parents, caregivers, or
families; foster care, kinship, adoption, reunification, or child welfare; housing/homelessness;
food or material needs; healthcare access; youth mental health; education access; poverty or
family economic stability; or emergencies affecting children/families. Generic business, sports,
elections, or adult-only content is false unless the source establishes a clear connection.
""",
)

direction = make_judge(
    name="direction",
    model=JUDGE_MODEL,
    feedback_value_type=Literal["correct", "defensible", "wrong"],
    instructions="""
From GO's perspective, is outputs.relevance_direction (opportunity | risk | watch) justified by
the source?  opportunity = an opening to recruit partners / build momentum; risk = may harm
children, families, child-welfare systems, or CarePortal; watch = relevant but not yet either.

Source: {{ inputs }}
Signal + chosen direction: {{ outputs }}

Return correct / defensible / wrong.
""",
)
# classification (signal_type + issue_labels) and place-resolution / cluster judges follow the
# same make_judge pattern (T6, T7, T8, T9); T4 reuses `relevance_gate` over eval_dropped_rows.

# --- Built-ins that need no rubric -----------------------------------------
safety = Safety(model=JUDGE_MODEL)
# Correctness(model=JUDGE_MODEL) is used ONLY on the gold subset (needs expectations).
```

> **Template variables** in `make_judge` are restricted to `{{ inputs }}`, `{{ outputs }}`,
> `{{ expectations }}`, `{{ trace }}` — not arbitrary column names — so we pack the relevant
> columns into the `inputs`/`outputs` structs when building the DataFrame.

## B4. Running it & logging to MLflow

```python
import mlflow
from pyspark.sql import functions as F

mlflow.set_experiment("/Shared/go-project/silver-eval")

# Pack columns into the inputs/outputs (/expectations) structs the harness expects.
data = (spark.table(f"{cat}.{sch}.eval_signal_rows")
        .select(
            F.struct("chunk_text", "source", "title", "source_type").alias("inputs"),
            F.struct("summary", "why_go", "quote", "relevance_direction",
                     "signal_type", "issue_labels").alias("outputs"),
        ))

with mlflow.start_run(run_name=f"silver-eval @ {model_tag}"):
    mlflow.log_params({"extract_model": extract_model, "judge_model": JUDGE_MODEL,
                       "confidence_threshold": 0.4, "pipeline_version": PIPELINE_VERSION})
    result = mlflow.genai.evaluate(
        data=data,
        scorers=[grounding, quote_support, relevance_gate, direction, safety],
    )
    print(result.metrics)          # aggregate pass rates per scorer

# Per-row detail is stored as traces+assessments; persist a flat copy for trend/SQL:
traces = mlflow.search_traces(run_id=result.run_id)
(spark.createDataFrame(traces)
   .write.mode("append").saveAsTable(f"{cat}.{sch}.eval_results"))
```

- Each run is tagged with **extract model + judge model + threshold + pipeline version** so we can
  compare across those axes (directly answers A1.5 threshold tuning and A1.6 haiku-vs-sonnet).
- `result.metrics` → aggregate pass rate per scorer; `mlflow.search_traces` → per-row feedback.
  Persisting to `eval_results` lets the funnel dashboard trend quality over time and even lets the
  app surface it.

## B5. Deterministic funnel & quality table (cheap, complementary)

Before any LLM judge, a **pure-SQL funnel notebook** answers "where do signals die / how healthy is
resolution" for near-zero cost — the other half of "robustness". One row per run:

| Metric | Source |
|--------|--------|
| chunks in / extractions errored / unparseable | `silver_signal_extractions` |
| `is_go_relevant` = true / ≥ threshold / grounded (quote found) / final signals | re-parse + `silver_signals` |
| signals-per-document distribution (flags A1.1) | `silver_signals` |
| `%` places `unresolved` (`u_` ids / null lat-lon) | `silver_places` |
| `%` orgs/policies `llm_unassigned` | `silver_organizations`/`silver_policies` |
| `%` single-signal events vs. multi (corroboration) | `silver_events` |

This runs every pipeline execution; the LLM-judge eval runs on demand.

## B6. Ground truth & calibration (the honest caveat)

LLM judges are not oracles. To trust them:
1. Hand-label a **small gold set** (~30–50 signals): `is_go_relevant`, correct `direction`,
   correct `issue`, and 1–3 `expected_facts` for `Correctness`.
2. Run the judges over the gold set and measure **judge ↔ human agreement**; tune rubric /
   lower judge temperature / add few-shot examples until agreement is acceptable.
3. Only then read the full-corpus judge scores as quality signal. Re-check agreement whenever the
   judge model or rubric changes.

## B7. Where it lives

```
go_opps/eval.py                     # judge/scorer definitions + rubrics (versioned in the wheel)
notebooks/eval/00_funnel.py         # B5 deterministic funnel/quality table (runs each pipeline)
notebooks/eval/01_build_datasets.py # B2 eval_signal_rows / eval_dropped_rows / resolution rows
notebooks/eval/02_run_judges.py     # B3/B4 mlflow.genai.evaluate over the datasets
resources/eval_job.yml              # bundle job (offline; not in the silver critical path)
```

## B8. Phased implementation

- **Phase 0 (fast, deterministic):** `00_funnel.py` + `eval_funnel` table. Immediately exposes the
  A1.1 / A1.3 / A1.7 recall losses and A2.1/A2.3 resolution health — no LLM cost.
- **Phase 1 (reference-free judges):** `go_opps/eval.py` + `01`/`02` for T1–T3, T5, T6, T11 on a
  stratified sample; wire the MLflow experiment. First real quality numbers.
- **Phase 2 (resolution/clustering):** T7–T9 over the (small) dimension/event tables.
- **Phase 3 (recall + calibration):** T4 over dropped rows; gold set + `Correctness` (T10) + judge
  calibration (B6). Now the confidence threshold (A1.5) and model choice (A1.6) can be tuned
  against numbers.
- **Phase 4 (act on findings):** fix A1.1 (multi-signal), A1.3 (normalized grounding), A2.4
  (graceful degradation), re-run eval, compare runs in MLflow.

## B9. Open decisions

- **Judge model** — `databricks-claude-sonnet-4-5` (proposed, strong) vs. a cheaper judge; keep it
  a widget so runs can compare.
- **Sample size / cost budget** for the quality judges (150–250 rows proposed).
- **Gold-set size & who labels it** (needed for `Correctness` + calibration).
- **Run cadence** — ad hoc for the hackathon; nightly or pipeline-gating later.
- Whether to also **fix A1.1/A1.3 first** (so the eval scores the improved pipeline) or eval the
  current one first to get a baseline — recommend **baseline first**, then fix, then compare.
```
