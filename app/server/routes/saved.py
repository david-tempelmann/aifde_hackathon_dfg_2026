"""App-state endpoints — saved opportunities (bookmarks + status/note) and saved drafts.

Writes go to the app-SP-owned `app` schema (Gold stays read-only). The current
user comes from the Databricks Apps forwarded-identity headers.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import config, db

router = APIRouter()

_STATUSES = {"new", "contacted", "in_progress", "done"}


def _user(request: Request) -> str:
    """Logged-in user from Databricks Apps headers; falls back for local dev."""
    for header in ("X-Forwarded-Email", "X-Forwarded-Preferred-Username", "X-Forwarded-User"):
        value = request.headers.get(header)
        if value:
            return value
    return config.get_pguser()  # local dev: the profile user


class SaveRequest(BaseModel):
    status: str | None = None
    note: str | None = None


class DraftSaveRequest(BaseModel):
    variant: str | None = None
    channel: str | None = None
    language: str | None = None
    content: str


def _validate_status(status: str | None) -> None:
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_STATUSES)}")


@router.get("/saved")
def list_saved(request: Request):
    """Saved opportunities for the current user, joined to Gold card details."""
    rows = db.query(
        f"""
        select s.opportunity_id, s.status, s.note, s.updated_at,
               c.title, c.state, c.place_name, c.issue_label,
               c.relevance_direction, c.priority_score, c.event_date
        from app.saved_opportunities s
        left join {config.GOLD_SCHEMA}.opportunity_cards c
               on c.opportunity_id = s.opportunity_id
        where s.user_email = %(u)s
        order by s.updated_at desc
        """,
        {"u": _user(request)},
    )
    return {"count": len(rows), "saved": rows}


@router.get("/saved/ids")
def saved_ids(request: Request):
    """Just the saved ids + status for the current user (to flag cards)."""
    rows = db.query(
        "select opportunity_id, status from app.saved_opportunities where user_email = %(u)s",
        {"u": _user(request)},
    )
    return {"saved": rows}


@router.post("/signals/{opportunity_id}/save")
def save_opportunity(opportunity_id: str, body: SaveRequest, request: Request):
    """Bookmark an opportunity (upsert); preserves existing fields when omitted."""
    _validate_status(body.status)
    rows = db.execute(
        """
        insert into app.saved_opportunities (opportunity_id, user_email, status, note)
        values (%(id)s, %(u)s, coalesce(%(status)s, 'new'), %(note)s)
        on conflict (user_email, opportunity_id) do update
          set status = coalesce(%(status)s, app.saved_opportunities.status),
              note   = coalesce(%(note)s, app.saved_opportunities.note),
              updated_at = now()
        returning opportunity_id, status, note, updated_at
        """,
        {"id": opportunity_id, "u": _user(request), "status": body.status, "note": body.note},
    )
    return rows[0]


@router.patch("/saved/{opportunity_id}")
def update_saved(opportunity_id: str, body: SaveRequest, request: Request):
    _validate_status(body.status)
    rows = db.execute(
        """
        update app.saved_opportunities
           set status = coalesce(%(status)s, status),
               note   = coalesce(%(note)s, note),
               updated_at = now()
         where user_email = %(u)s and opportunity_id = %(id)s
        returning opportunity_id, status, note, updated_at
        """,
        {"id": opportunity_id, "u": _user(request), "status": body.status, "note": body.note},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Not saved")
    return rows[0]


@router.delete("/saved/{opportunity_id}")
def unsave_opportunity(opportunity_id: str, request: Request):
    db.execute(
        "delete from app.saved_opportunities where user_email = %(u)s and opportunity_id = %(id)s",
        {"id": opportunity_id, "u": _user(request)},
    )
    return {"ok": True}


@router.post("/signals/{opportunity_id}/save-draft")
def save_draft(opportunity_id: str, body: DraftSaveRequest, request: Request):
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Empty draft")
    rows = db.execute(
        """
        insert into app.saved_drafts (opportunity_id, user_email, variant, channel, language, content)
        values (%(id)s, %(u)s, %(variant)s, %(channel)s, %(language)s, %(content)s)
        returning id, created_at
        """,
        {
            "id": opportunity_id,
            "u": _user(request),
            "variant": body.variant,
            "channel": body.channel,
            "language": body.language,
            "content": body.content,
        },
    )
    return rows[0]


@router.get("/saved/drafts")
def list_drafts(request: Request, opportunity_id: str | None = None):
    clause = "and opportunity_id = %(id)s" if opportunity_id else ""
    rows = db.query(
        f"""
        select id, opportunity_id, variant, channel, language, content, created_at
        from app.saved_drafts
        where user_email = %(u)s {clause}
        order by created_at desc
        """,
        {"u": _user(request), "id": opportunity_id},
    )
    return {"count": len(rows), "drafts": rows}
