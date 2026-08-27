"""Overview / hotspot aggregates for the dashboard page."""

from __future__ import annotations

from fastapi import APIRouter

from .. import config, db, queries

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
    """Header KPIs: total signals + change since the previous recorded day.

    Records today's total in app.signal_count_history, then diffs against the
    most recent earlier day. `since_yesterday` is null until there's history.
    """
    total = db.query(f"select count(*)::int as n from {config.GOLD_SCHEMA}.opportunity_cards")[0]["n"]
    db.execute(
        """
        insert into app.signal_count_history (day, total) values (current_date, %(t)s)
        on conflict (day) do update set total = excluded.total, recorded_at = now()
        """,
        {"t": total},
    )
    prior = db.query(
        "select total from app.signal_count_history where day < current_date order by day desc limit 1"
    )
    since_yesterday = (total - prior[0]["total"]) if prior else None
    return {"total": total, "since_yesterday": since_yesterday}
