# GO Project — Outreach Signals: Implemented Features

The **Outreach Signals** app (WP3) is a Databricks App (React + FastAPI) that helps GO
Project State Directors discover, prioritise, and act on region-specific legislative and
community signals — each cited, dated, scored, and tied to a place and an issue. It reads
curated **Contract B Gold** tables from Lakebase (Postgres) via a SQL/psycopg layer.

This is a running list of what's built.

---

## Signals feed (core dashboard)

- **State swim lanes.** Signals are grouped by state, and within each state split into three
  columns — **Opportunity / Risk / Watch** — for at-a-glance triage.
- **Concise signal cards.** Each card shows the issue (with a category icon), a priority
  gauge, a one-line summary, place, date, and a confidence bar. Uniform sizing keeps the
  board scannable.
- **Priority as a gauge.** A small circular 0–100 gauge (warm→gold→slate) makes the
  priority score instantly readable; labelled "Priority" vs "Confidence" so they're not confused.
- **Show more per lane.** Each column caps at 3 cards with a "+N more" expander.
- **Focus state.** Hovering a card dims the rest of the state's cards to help you read dense text.

## Map (region scoping)

- **Mainland-US choropleth.** State polygons (Alaska/Hawaii dropped) shaded in one hue;
  states with signals are coloured with their own palette colour.
- **Per-state clusters → drill-in.** Zoomed out, each state shows a single numbered dot
  (signal count); clicking a state (or its dot) **filters to that state** and expands into
  individual dots. A "Go back to full view" control returns to the locked whole-US overview.
- **Hover summaries.** Hovering a state shows a tooltip with its totals, the
  opportunity/risk/watch split, and the top issue.
- **Polish.** Numbered clusters gently pulse; dots have a soft glow; the map/list is toggleable.

## Filters

- **Sidebar filter panel** with a search box and collapsible sections.
- **Multi-select tag filters** for Direction, State, Issue, and Signal type (OR within a
  group, AND across groups), each with live counts and category icons.
- **Confidence buckets** — High / Medium / Low, each with a plain-language description for
  non-technical users.
- **Sort** by Priority / Most recent / Highest confidence.
- Filtering/sorting is **client-side and instant**; the map, swim lanes, and Overview all
  react to the active filters. Overview matrix cells deep-link into a pre-filtered feed.

## Signal detail drawer (citations)

- Slide-over panel with the full summary, **why it matters to GO**, a **recommended action**,
  metadata (issue, type, place, dates, source, confidence), and affected populations.
- **Citations as first-class evidence** — the exact source quote with an **"Open exact
  passage"** deep link built as a URL **Text Fragment**, so the browser scrolls to and
  highlights the sentence on the live source page (falls back to the plain source URL).

## Action Studio (outreach drafts)

From the signal detail drawer, a State Director can generate ready-to-send **outreach drafts**
that turn a signal into partner recruitment for CarePortal — grounded, editable, and
translatable. It closes the loop from "here's a signal" to "here's the message you send."

### Draft options the user controls

- **Recipient (optional)** — a free-text partner name (e.g. "Grace Community Church"). When set,
  the drafts address that recipient; when blank they address "a prospective CarePortal partner."
- **Channel / format variants** — chosen as multi-select chips; each is a distinct
  channel + tone + length spec. Available variants:
  - **Email** — warm, community-minded, with a subject line (120–170 words)
  - **Short message** — concise peer-to-peer DM, no subject (60–90 words)
  - **SMS** — friendly and direct, under 320 characters
  - **Community call-to-action** — punchy public post/flyer blurb in second person
  - **Formal letter** — professional, precise, with a subject line (130–180 words)
  - **Phone-call script** — spoken opener, talking points, and a closing ask
  - Email, Short message, and Community call-to-action are on by default.
- **Generate / Regenerate** produces one draft per selected variant.

### How it's implemented

- **Grounded generation.** The backend (`llm.py`) builds a context block from the opportunity's
  own fields (summary, issue, place, why-it-matters-to-GO, recommended action, affected
  populations) plus its **citations**, and a small server-side set of **approved GO/CarePortal
  facts**. A strict system prompt forbids inventing statistics, names, dates, or quotes — the
  model may only use what's in the signal, its citations, and those approved facts.
- **Model.** Each variant is one chat call to a Databricks **Foundation Model serving endpoint**
  (`SERVING_ENDPOINT`). Selected variants are generated **in parallel** (thread pool) to keep
  latency down, then returned in the order requested.
- **Human-in-the-loop.** Every draft is clearly flagged as AI-generated; each renders in an
  **editable textarea** with a one-click **Copy** button. Nothing is sent automatically —
  the worker reviews, edits, and copies out.
- **Endpoints.** `GET /draft/options` (variants + defaults) and
  `POST /signals/{opportunity_id}/draft` (`partner_name`, `variants`) → drafts + citations.

### Translate feature

Any draft can be localized for the multilingual communities GO serves:

- **Target languages** — Spanish, Chinese, Vietnamese, Korean, Arabic, Russian, French,
  Portuguese (curated for NY/CA/VA communities), picked from an English → language selector.
- **Translation engine** — the app calls Databricks' built-in **`ai_translate`** SQL function
  on a serverless **SQL warehouse** (via the Statement Execution API), since Lakebase/Postgres
  has no such function. The *edited* draft text is what gets translated, so the worker's edits
  carry through.
- **Quality & cultural-fit score** — a second **LLM-as-judge** call rates each translation 0–100
  on accuracy, fluency, and cultural appropriateness for a community audience, and returns a
  short **reviewer note** on any wording to adjust. The score is shown as a colour-coded badge
  (green ≥80, amber ≥60, rose below) so a non-native speaker can gauge whether the translation is
  safe to send.
- The translated text is itself editable and independently copyable.
- **Endpoints.** `GET /translate/languages` and `POST /translate` (`text`, `target_lang`) →
  translated text, score, and assessment.

## Overview / analysis

- **KPI cards** — Total signals, Opportunities, Risks, Watch, and Latest, with icons and a
  count-up animation.
- **Issue × State hotspot matrix** — the "knowledge-graph-lite" meta-analysis view: rows =
  issues, columns = states, cells shaded by signal density with an opportunity/risk/watch
  bar. Rows and columns are derived from whatever is currently in the data. **Clicking a
  cell** jumps to the Signals feed pre-filtered to that issue + state.

## Look & feel

- **Frosted-glass top bar** over soft CarePortal-coloured shapes, with the app logo, nav, and
  a muted-orange active-tab state.
- CarePortal brand palette (navy / brand blue / orange / gold) and Inter throughout.
- **Skeleton loaders** while data loads; subtle **entrance animations** and card hover-lift.

---

## Data & platform

- **Databricks App** (React + FastAPI, served as a single app) with dual-mode auth: CLI
  profile locally, injected service-principal credentials when deployed.
- **Lakebase (autoscaling Postgres)** holds the Contract B Gold serving tables; the app reads
  them through a psycopg connection pool, minting a fresh OAuth token per connection.
- **UC → Lakebase sync.** The Gold Delta tables are replicated into the Lakebase `gold` schema
  via **synced tables** (SNAPSHOT policy — full re-copy per run, robust to the Gold job's
  `CREATE OR REPLACE` rebuilds).
- **Scheduled refresh.** A `gold_refresh` job (daily) triggers all five sync pipelines so the
  app automatically reflects the latest Gold. Read access for the app service principal is
  granted once and persists across routine refreshes.
- **Infrastructure as code.** App, Lakebase project/branch, synced tables, and the refresh job
  are all declared in the Databricks Asset Bundle (`databricks.yml` + `resources/`).
