# aifde_hackathon_dfg_2026

GO Project outreach-insights solution, built as a [Databricks Asset Bundle](https://docs.databricks.com/dev-tools/bundles/index.html).

> 📊 **[Project overview](docs/project-overview.html)** — a diagram-focused walkthrough of the whole
> solution: end-to-end pipeline, ingestion, entity extraction & resolution, the app layer, evaluation,
> and the data-model decisions. Open it in a browser.

## Layout

- `notebooks/` — Databricks notebooks (`.py` source format for clean diffs).
- `go_opps/` — Python package; built into a wheel and installed on jobs.
- `app/` — the **Outreach Insights** Databricks App: FastAPI backend + React (Vite/TS/Tailwind) frontend.
- `resources/` — one YAML file per bundle resource (jobs, app, etc.); all are auto-included.
- `databricks.yml` — bundle definition: variables, artifacts, sync excludes, and the `dev` target.

## The app (`app/`)

A two-page Databricks App for GO Project outreach teams:

- **Signals** — the core page: a filterable feed of region-scoped legislative/community signals,
  each with issue, place, relevance direction (opportunity / risk / watch), confidence, a
  "why GO cares" rationale, and a **cited quote deep-linked to the source** (URL Text Fragment).
- **Overview** — headline counts + an issue × state hotspot matrix (NY / CA / VA).

**Data path:** the FastAPI backend reads the **Contract B Gold serving tables from an
autoscaling Lakebase** (Postgres, via a `psycopg` pool). The Lakebase project/branch are
declared in-bundle (`resources/lakebase.yml`), and the app attaches through a `postgres`
app-resource block (`resources/app.yml`) that injects the `PG*` env vars. Auth is dual-mode —
a CLI profile locally, the app's injected service principal when deployed — and the DB
password is a fresh OAuth token minted per connection.

The Gold DDL + hand-seeded sample rows live in `app/lakebase/contract_b.sql` (schema `gold`
in `databricks_postgres`): `opportunity_cards`, `opportunity_details`, `opportunity_citations`,
plus `dim_issues` / `dim_places`. Re-seed with:
```bash
HOST=$(databricks postgres list-endpoints projects/go-outreach/branches/production -p fe-vm-ai-fde-hackathon -o json | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['status']['hosts']['host'])")
TOKEN=$(databricks postgres generate-database-credential projects/go-outreach/branches/production/endpoints/primary -p fe-vm-ai-fde-hackathon -o json | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
PGPASSWORD=$TOKEN psql "host=$HOST dbname=databricks_postgres user=$(whoami)@databricks.com sslmode=require" -f app/lakebase/contract_b.sql
```

**Local dev** (PG\* + profile from your shell):
```bash
cd app && uv sync
DATABRICKS_PROFILE=fe-vm-ai-fde-hackathon PGHOST=<endpoint-host> PGUSER=<you@databricks.com> \
  uv run uvicorn app:app --reload --port 8000                # backend
cd frontend && npm install && npm run dev                    # frontend (proxies /api)
```

## Key decisions

- **Catalog/schema are bundle variables** (`ai_fde_hackathon_catalog` / `brickhearts`), passed to notebooks as parameters so they're easy to override per target.
- **`go_opps` ships as a wheel artifact** (`uv build --wheel`). The bundle uploads it and rewrites the dependency to the workspace path, so `dist/` is never synced.
- **Jobs run on serverless (environment v4)**; the wheel is attached via a job `environment` referenced by the notebook task's `environment_key`.
- **`dev` target uses `mode: development`**, so deploys are namespaced per user and schedules are paused.

## Develop & deploy

First, set up a CLI profile for this workspace (name it whatever you like):

```bash
databricks auth login -p <your-profile-name>
```

Then use the makefile to deploy:

```bash
make install          # create the venv and install deps with uv
make deploy           # build the frontend + wheel, deploy the bundle to dev
make deploy-all       # deploy, then start the app via `bundle run`
```

`make deploy` builds `app/frontend/dist` before deploying; `make deploy-all` also starts the
app (`APP=go_outreach_app` by default). Override the auth profile with `PROFILE=<name>` if
needed. On first deploy, grant the app's service principal read access to the schema:

```sql
GRANT USE CATALOG ON CATALOG ai_fde_hackathon_catalog TO `<app-sp-client-id>`;
GRANT USE SCHEMA  ON SCHEMA  ai_fde_hackathon_catalog.brickhearts TO `<app-sp-client-id>`;
GRANT SELECT      ON SCHEMA  ai_fde_hackathon_catalog.brickhearts TO `<app-sp-client-id>`;
```

Find the client id with `databricks apps get go-outreach-app` (`service_principal_client_id`).
