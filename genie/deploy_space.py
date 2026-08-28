#!/usr/bin/env python3
"""Create or update the GO Outreach Topic Deep-Dive Genie space from its repo definition.

The space definition lives in `genie/outreach_topic_agent.json` (version-controlled,
reviewable). This script wraps it into the Genie REST API request shape — the inner
`serialized_space` is JSON-encoded to a string — and creates a new space or patches an
existing one in place.

Usage:
    # create a new space (prints the new space_id)
    python3 genie/deploy_space.py --profile fe-vm-ai-fde-hackathon

    # update an existing space in place (keeps the same id + URL)
    python3 genie/deploy_space.py --profile fe-vm-ai-fde-hackathon --space-id <id>

Point the app at the resulting id via GENIE_SPACE_ID (config default / app.yaml env).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

DEFN = pathlib.Path(__file__).with_name("outreach_topic_agent.json")


def _api(method: str, path: str, profile: str, body: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(body, f)
        tmp = f.name
    out = subprocess.run(
        ["databricks", "api", method, path, "--profile", profile, "--json", f"@{tmp}"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        sys.exit(f"API {method} {path} failed:\n{out.stderr or out.stdout}")
    return json.loads(out.stdout) if out.stdout.strip() else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="fe-vm-ai-fde-hackathon")
    ap.add_argument("--space-id", help="update this existing space instead of creating a new one")
    args = ap.parse_args()

    defn = json.loads(DEFN.read_text())
    # The Genie API takes serialized_space as a JSON-encoded string.
    body = {
        "title": defn["title"],
        "description": defn["description"],
        "warehouse_id": defn["warehouse_id"],
        "serialized_space": json.dumps(defn["serialized_space"]),
    }

    if args.space_id:
        resp = _api("patch", f"/api/2.0/genie/spaces/{args.space_id}", args.profile, body)
        space_id = args.space_id
        action = "updated"
    else:
        body["parent_path"] = defn["parent_path"]
        resp = _api("post", "/api/2.0/genie/spaces", args.profile, body)
        space_id = resp.get("space_id", "?")
        action = "created"

    print(f"Space {action}: {space_id}")
    print(f"  title: {defn['title']}")
    print(f"  set GENIE_SPACE_ID={space_id} for the app to use it.")


if __name__ == "__main__":
    main()
