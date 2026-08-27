"""FastAPI entry point for the GO Project outreach-insights app.

Serves the built React SPA plus a JSON API backed by the Contract B Gold tables
in Lakebase. Run locally with (PG* + profile from your shell):

    DATABRICKS_PROFILE=fe-vm-ai-fde-hackathon PGHOST=<endpoint-host> \
      PGUSER=<you@databricks.com> uv run uvicorn app:app --reload --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server import db
from server.db import pool
from server.routes import draft, overview, saved, signals, translate


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=30.0)  # fail fast if Lakebase is unreachable
    try:
        db.bootstrap_app_state()  # create writable app-state schema (non-fatal)
    except Exception as exc:  # never block read endpoints on app-state setup
        print("[lifespan] app-state bootstrap skipped:", exc)
    yield
    pool.close()


app = FastAPI(title="GO Project — Outreach Insights", lifespan=lifespan)

app.include_router(signals.router, prefix="/api")
app.include_router(overview.router, prefix="/api")
app.include_router(draft.router, prefix="/api")
app.include_router(translate.router, prefix="/api")
app.include_router(saved.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the built React frontend (frontend/dist) when present.
_FRONTEND = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_FRONTEND):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_FRONTEND, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # SPA fallback — any non-API path returns index.html for client routing.
        return FileResponse(os.path.join(_FRONTEND, "index.html"))
