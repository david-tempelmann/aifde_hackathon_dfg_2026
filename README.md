# aifde_hackathon_dfg_2026

GO Project outreach-insights solution, built as a [Databricks Asset Bundle](https://docs.databricks.com/dev-tools/bundles/index.html).

## Layout

- `notebooks/` — Databricks notebooks (`.py` source format for clean diffs).
- `go_opps/` — Python package; built into a wheel and installed on jobs.
- `resources/` — one YAML file per bundle resource (jobs, etc.); all are auto-included.
- `databricks.yml` — bundle definition: variables, artifacts, and the `dev` target.

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
make deploy           # build the wheel + deploy the bundle to dev
make deploy-all       # deploy, then start app(s) via `bundle run` (once defined)
```
