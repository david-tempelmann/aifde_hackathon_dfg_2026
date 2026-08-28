"""Outreach-draft (Action Studio) endpoints — grounded generation over Gold."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config, db, llm, queries

router = APIRouter()


class DraftRequest(BaseModel):
    partner_name: str | None = None
    variants: list[str] | None = None  # variant keys; defaults to the starter set


@router.get("/draft/options")
def draft_options():
    """Available outreach variants (for the UI) + which are on by default."""
    return {
        "variants": [
            {"key": k, "label": v["label"], "channel": v["channel"]}
            for k, v in llm.VARIANTS.items()
        ],
        "defaults": llm.DEFAULT_VARIANTS,
    }


@router.post("/signals/{opportunity_id}/draft")
def draft_outreach(opportunity_id: str, body: DraftRequest):
    """Generate grounded outreach drafts for an opportunity."""
    opp_rows = db.query(queries.one_opportunity_query(), {"id": opportunity_id})
    if not opp_rows:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opp = opp_rows[0]
    citations = db.query(queries.CITATIONS_QUERY, {"id": opportunity_id})

    drafts = llm.draft_variants(
        opp,
        citations,
        variant_keys=body.variants,
        partner_name=body.partner_name,
    )
    return {
        "opportunity_id": opportunity_id,
        "model": config.SERVING_ENDPOINT,
        "drafts": drafts,
        "citations": citations,
    }
