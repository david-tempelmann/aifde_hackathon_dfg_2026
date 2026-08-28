#!/usr/bin/env python3
"""Grant the deployed app's service principal the access Genie + SQL need.

Databricks Apps run the Deep-Dive Genie flow (and any Databricks SQL calls) as
the *app's own service principal*, not as the user who deployed. That SP needs:

  1. CAN_USE on the SQL warehouse the Genie space runs on — otherwise Genie
     `start-conversation` returns 403.
  2. USE CATALOG + USE SCHEMA + SELECT on the schema the Genie space queries —
     otherwise the Genie query completes with status FAILED (no table access).

The app-resource `sql_warehouse ... CAN_USE` block in resources/app.yml does NOT
create the warehouse *permission-ACL* entry Genie checks, and the `brickhearts`
schema is created by the silver/gold notebooks (not the bundle), so neither grant
can be expressed as a bundle `grants` block. This script closes that gap: it
resolves the current app SP from the bundle and re-applies both grants. It is
idempotent (permission PATCH merges; GRANT is a no-op if already held), so
`make deploy-all` runs it after every deploy — the grants survive redeploys and,
if the app is ever recreated with a fresh SP, are simply re-applied.

The app name is pinned in resources/app.yml (`name: brickhearts-goproject-outreach`),
so normal redeploys keep the same SP and these grants persist untouched.

Usage:
    python3 scripts/grant_app_permissions.py --target dev --profile fe-vm-ai-fde-hackathon
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def _run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{out.stderr or out.stdout}")
    return out.stdout


def _api(method: str, path: str, profile: str, body: dict) -> dict:
    out = _run(["databricks", "api", method, path, "--profile", profile, "--json", json.dumps(body)])
    return json.loads(out) if out.strip() else {}


def _sql(warehouse_id: str, profile: str, statement: str) -> None:
    resp = _api(
        "post",
        "/api/2.0/sql/statements",
        profile,
        {"warehouse_id": warehouse_id, "statement": statement, "wait_timeout": "30s"},
    )
    status = resp.get("status", {})
    state = status.get("state")
    if state != "SUCCEEDED":
        sys.exit(f"GRANT failed ({state}): {status.get('error', {}).get('message', '')}\n  {statement}")
    print(f"  ✓ {statement}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="fe-vm-ai-fde-hackathon")
    ap.add_argument("--target", default="dev")
    ap.add_argument("--app-key", default=None, help="bundle app resource key (defaults to the only app)")
    args = ap.parse_args()

    # Pull the app name + catalog/schema/warehouse straight from the bundle so
    # this stays in sync with databricks.yml / resources/app.yml.
    summary = json.loads(
        _run(["databricks", "bundle", "summary", "-t", args.target, "-p", args.profile, "-o", "json"])
    )
    apps = summary.get("resources", {}).get("apps", {})
    if not apps:
        sys.exit("No apps found in bundle summary — deploy the app first.")
    app_key = args.app_key or next(iter(apps))
    app_name = apps[app_key]["name"]

    def var(name: str) -> str:
        v = summary.get("variables", {}).get(name, {})
        return v.get("value") or v.get("default")

    catalog, schema, warehouse_id = var("catalog"), var("schema"), var("warehouse_id")

    # Resolve the app's runtime service principal (created when the app was created).
    app = json.loads(_run(["databricks", "apps", "get", app_name, "--profile", args.profile]))
    sp = app.get("service_principal_client_id")
    if not sp:
        sys.exit(f"App {app_name!r} has no service_principal_client_id yet — is it deployed?")

    print(f"App {app_name!r} SP: {sp}")
    print(f"Warehouse {warehouse_id} → CAN_USE")
    _api(
        "patch",
        f"/api/2.0/permissions/warehouses/{warehouse_id}",
        args.profile,
        {"access_control_list": [{"service_principal_name": sp, "permission_level": "CAN_USE"}]},
    )
    print("  ✓ CAN_USE granted")

    print(f"Schema {catalog}.{schema} → USE + SELECT")
    for stmt in (
        f"GRANT USE CATALOG ON CATALOG {catalog} TO `{sp}`",
        f"GRANT USE SCHEMA ON SCHEMA {catalog}.{schema} TO `{sp}`",
        f"GRANT SELECT ON SCHEMA {catalog}.{schema} TO `{sp}`",
    ):
        _sql(warehouse_id, args.profile, stmt)

    print("Done — app SP has the warehouse + schema access Genie needs.")


if __name__ == "__main__":
    main()
