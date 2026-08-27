# GO Project — Development Plan (v0.1, WIP)

> 🚧 **Work in progress / to be decided.** A first proposal for splitting the 2-day hackathon
> into parallel work packages. Companion to [`solution-design.md`](./solution-design.md).
> Names, scope, and boundaries are all open for discussion.

## Guiding idea: agree the contracts at hour 0, then each track self-bootstraps

The tracks run in parallel only if we **fix the two handoff schemas first** (even loosely) —
and if **no track depends on another person to get started**. So each track owns a tiny
bootstrap step against the contracts; nobody waits on the 4th person.

- **Contract A — `silver.documents` + `silver.chunks`** (WP1 → WP2): `document_id, source_url,
  retrieved_at, clean_text, state` + `chunk_id, document_id, char_start, char_end, text`.
- **Contract B — Gold serving tables in Lakebase** (WP2 → WP3): `opportunity_cards`,
  `opportunity_details`, `opportunity_citations` (+ dimensions/bridges).

*(Contracts are minimal and will evolve — the point is a stable-enough shape to unblock parallel work.)*

## Day 1 — three self-sufficient tracks (+ optional 4th, later)

| WP | Scope (Day 1) | Self-bootstrap (hour 0, no external dependency) | Produces (contract) |
|----|---------------|--------------------------------------------------|---------------------|
| **WP1 — Ingest → chunks** | Scrape target pages, clean HTML, chunk → `documents` / `chunks`. Bundle job. | Owner picks **2–3 sample URLs** per state themselves to start. | **Contract A** tables |
| **WP2 — Extract → Gold** `M`/`S` | Entity extraction + resolution (Signal/Issue/Place), incl. **relevance direction** (opportunity/risk/watch) + legislative signal types, semantic/graph data model, ranking, Gold + Lakebase sync. **Owns the ontology baseline.** | Owner writes a handful of **synthetic docs/chunks** (a few legislative) + a **first-cut vocab** inline. | **Contract B** tables |
| **WP3 — App** `M` | Databricks App **core dashboard**, **state-scoped by default**: browse/filter signals (issue, place, time, confidence, opportunity vs. risk), detail view, citation rendering (Text-Fragment links), app shell + app-owned Lakebase tables (`app_state`). *(Action studio + graph views are Day 2.)* Assumes a first datamodel ≈ WP2's. | Owner **seeds Lakebase with sample rows** matching Contract B. | The app |
| **WP4 — Enhance** (optional, later) | **Non-blocking** improvements layered on top whenever the 4th person is free: expand source registry + robots/terms review, refine issue taxonomy/gazetteer, spot-check extraction quality, start demo story. | — depends on nothing; nothing depends on it | Better inputs + demo |

**Why this split works:** each of WP1/WP2/WP3 can start and finish Day 1 **alone**, against its
own tiny bootstrap seed, and integrate as the neighbouring track's real output appears. WP4 is
pure upside — it improves sources, taxonomy, and the demo, but the core never blocks on it.

## Day 2 — integrate, then the high-value features

First close the loop, then build the features that assume a working spine:

- **Integrate** — swap mocks for live tables (real WP1 output → WP2, real WP2 Gold → WP3).
- **Action studio** — grounded generation via `ai_query` over the selected signal's citations +
  approved GO facts; human-review before use. **Recruit-partner draft** `M`; **escalate**
  summary and **advocate / amended bill language** as stretch `C`.
- **Graph representation / UI / interaction** `S`/`C` (`solution-design.md` §8) — hotspot
  matrix, corroboration clusters, explained mini-graph; interactive/chat explorer is a stretch `Could`.

Then, as capacity allows (roughly priority order):

- **Robust entity resolution / NER** `C` — canonicalize places/orgs, tighten confidence.
- **Ranking & corroboration refinement** — tune the priority score; cross-source confidence.
- **Demo hardening** — a few strong "hero" opportunities working end-to-end with live citations.

## Requirement coverage check

| Requirement | Where |
|-------------|-------|
| Web scraping (NY/CA/VA) `M` | WP1 (+ WP4 source selection) |
| Outreach dashboard, region-specific `M` | WP3 (Day 1 core, state-scoped) |
| Outreach message drafting `M` | Day 2 (action studio — recruit draft) |
| Citations for all GenAI `M` | WP2 (produce) + WP3 (render) |
| Basic knowledge graph `S` | WP2 (data) + Day 2 (views) |
| Robust NER `C` | WP2 baseline + Day 2 (resolution) |
| Interactive graph interface `C` | Day 2 stretch |

## Open questions (to decide together)

- Contract A/B exact columns — lock a first version before splitting off.
- Each track self-bootstraps its own seed (URLs / synthetic docs / sample rows) — confirm that's the plan, not a shared upfront task.
- How real does WP1 scraping need to be Day 1 vs. a few pages by hand? (`Won't-have`: robust scraping.)
