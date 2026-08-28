"""Overview / hotspot aggregates for the dashboard page."""

from __future__ import annotations

from fastapi import APIRouter

from .. import db, queries

router = APIRouter()


@router.get("/overview")
def overview():
    """Headline counts + issue x state hotspot matrix (NY/CA/VA)."""
    summary = db.cached_query("summary", queries.SUMMARY_QUERY)
    hotspots = db.cached_query("hotspots", queries.HOTSPOT_QUERY)
    return {
        "summary": summary[0] if summary else {},
        "hotspots": hotspots,
    }


@router.get("/stats")
def stats():
    """Total signal count for the header badge."""
    total = db.cached_query("stats_total", queries.STATS_QUERY)
    return {"total": total[0]["n"] if total else 0}
