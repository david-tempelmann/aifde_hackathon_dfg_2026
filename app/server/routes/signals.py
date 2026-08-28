"""Signal feed + filter-option endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from .. import db, queries

router = APIRouter()


@router.get("/signals")
def list_signals(
    state: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    issue: str | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    search: str | None = Query(default=None),
    sort: str = Query(default="priority"),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Filtered, sorted signal feed — the core outreach page."""
    sql, params = queries.build_signals_query(
        state=state,
        direction=direction,
        issue=issue,
        signal_type=signal_type,
        min_confidence=min_confidence,
        search=search,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    rows = db.query(sql, params)
    return {"count": len(rows), "signals": rows}


@router.get("/filters")
def filter_options():
    """Distinct values (with counts) for the UI filter controls."""
    rows = db.cached_query("filters", queries.FILTERS_QUERY)
    options: dict[str, list[dict]] = {}
    for row in rows:
        options.setdefault(row["kind"], []).append(
            {"value": row["value"], "count": row["n"]}
        )
    return options
