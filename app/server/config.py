"""Runtime configuration and dual-mode auth for the Lakebase Gold backend.

The app reads Contract B Gold tables from an autoscaling Lakebase (Postgres).
It runs in two environments:

- **Databricks Apps** — the `postgres` app-resource attach injects the PG* env
  vars (PGHOST/PGUSER/PGPORT/PGDATABASE/PGSSLMODE); the DB token is minted for
  the app's own service principal.
- **Local dev** — PG* come from the shell env; auth uses a CLI profile
  (`DATABRICKS_PROFILE`, default `fe-vm-ai-fde-hackathon`). If PGUSER isn't set,
  it defaults to the profile's user email.

The DB password is a fresh OAuth bearer token (`config.authenticate()`), minted
per connection — the verified autoscaling attach pattern.
"""

from __future__ import annotations

import functools
import os

from databricks.sdk import WorkspaceClient

IS_DATABRICKS_APP: bool = bool(os.environ.get("DATABRICKS_APP_NAME"))

# Postgres connection params (injected by the attach when deployed).
PGHOST: str = os.environ.get("PGHOST", "")
PGPORT: str = os.environ.get("PGPORT", "5432")
PGDATABASE: str = os.environ.get("PGDATABASE", "databricks_postgres")
PGSSLMODE: str = os.environ.get("PGSSLMODE", "require")

# Gold objects live in this schema (see app/lakebase/contract_b.sql).
GOLD_SCHEMA: str = os.environ.get("GO_GOLD_SCHEMA", "gold")

# Foundation Model serving endpoint used for the outreach-draft action.
SERVING_ENDPOINT: str = os.environ.get("SERVING_ENDPOINT", "databricks-claude-sonnet-4-5")

# SQL warehouse used for AI SQL functions (ai_translate) — Databricks SQL only.
WAREHOUSE_ID: str = os.environ.get("DATABRICKS_WAREHOUSE_ID", "41659c95dacd3bf0")


@functools.lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    """Authenticated client — app SP remotely, CLI profile locally."""
    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "fe-vm-ai-fde-hackathon")
    return WorkspaceClient(profile=profile)


@functools.lru_cache(maxsize=1)
def get_pguser() -> str:
    """Postgres role — injected PGUSER remotely, profile email locally."""
    user = os.environ.get("PGUSER")
    if user:
        return user
    return get_workspace_client().current_user.me().user_name


def get_db_token() -> str:
    """Fresh OAuth bearer token used as the Postgres password."""
    headers = get_workspace_client().config.authenticate()
    return headers.get("Authorization", "").removeprefix("Bearer ").strip()
