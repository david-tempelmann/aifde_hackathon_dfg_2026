# Genie space — Topic Deep-Dive

The Genie space that backs the app's **Deep Dive** page, defined as code so it's
version-controlled and reproducible (Genie spaces aren't a native Databricks Asset
Bundle resource, so we deploy it with a small script instead of the bundle).

## Files
- **`outreach_topic_agent.json`** — the full space definition (title, description,
  parent path, warehouse, and `serialized_space`: data sources + instructions). The
  `serialized_space` is stored as a readable object; the deploy script JSON-encodes it
  to the string the Genie API expects.
- **`deploy_space.py`** — create the space (prints the new `space_id`) or update an
  existing one in place.

## Deploy
```bash
# create a new space
python3 genie/deploy_space.py --profile fe-vm-ai-fde-hackathon

# update the existing space in place (same id + URL)
python3 genie/deploy_space.py --profile fe-vm-ai-fde-hackathon --space-id <id>
```

Point the app at the space via **`GENIE_SPACE_ID`** — the default in
`app/server/config.py` and the env in `app/app.yaml`. Current space:
`01f1a2e161fa111791babad65ae8955d`.

## The findings contract
The "canonical findings" query is defined in the space **instructions** (Genie
generates the SQL from them). It returns one result set with columns:

```
finding_type, subject, detail, metric, event_date, source, source_url, quote
```

`finding_type` ∈ `hot_place | named_responder | related_issue | upcoming_event |
funding_hook | crisis_signal`. Single-signal rows (`upcoming_event`, `funding_hook`,
`crisis_signal`) carry `source_url` + `quote` so the app deep-links back to the exact
source (URL Text Fragment); aggregate rows leave them null.

`app/server/genie.py` calls the space and serializes these rows into the payload the
`FindingsPanel` renders. To change the findings shape, edit the CANONICAL FINDINGS
instruction in `outreach_topic_agent.json`, re-run `deploy_space.py --space-id`, and
update the serializer/renderer to match.

> Forked from the `BrickHearts — Outreach Topic Agent` space (Julie's), which stays
> untouched; this repo-owned copy adds the `source_url` + `quote` citation columns.
