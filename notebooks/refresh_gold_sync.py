# Databricks notebook source
# Refresh the Lakebase Gold synced tables (SNAPSHOT policy → full re-copy per
# run). Finds the managed sync pipelines by their destination name and triggers
# an update on each, then waits for completion. A routine refresh reloads the
# tables in place, so the app SP's read grant persists — no re-grant needed here.
import time
from databricks.sdk import WorkspaceClient

MATCH = "ai_fde_hackathon_catalog.gold."
TIMEOUT_S = 900

w = WorkspaceClient()

pipelines = [p for p in w.pipelines.list_pipelines() if p.name and MATCH in p.name]
print(f"Found {len(pipelines)} Gold sync pipeline(s).")
if not pipelines:
    raise SystemExit("No Gold sync pipelines found — nothing to refresh.")

updates = {}
for p in pipelines:
    upd = w.pipelines.start_update(pipeline_id=p.pipeline_id)
    updates[p.pipeline_id] = {"name": p.name, "update_id": upd.update_id}
    print("triggered:", p.name)

deadline = time.time() + TIMEOUT_S
pending = set(updates)
while pending and time.time() < deadline:
    time.sleep(15)
    for pid in list(pending):
        state = str(w.pipelines.get_update(pipeline_id=pid, update_id=updates[pid]["update_id"]).update.state)
        if any(s in state for s in ("COMPLETED", "FAILED", "CANCELED")):
            print(updates[pid]["name"], "->", state)
            pending.discard(pid)

if pending:
    raise Exception("Timed out waiting for: " + ", ".join(updates[p]["name"] for p in pending))
print("All Gold synced tables refreshed.")
