"""SQL builders for the Contract B Gold serving tables (Lakebase / Postgres).

The feed joins opportunity_cards + opportunity_details + the primary citation and
aliases columns to the shape the frontend already consumes (so the UI is stable),
adding the Gold-only fields `recommended_action` and `priority_score`. Categorical
filters bind as psycopg named params; sort comes from a whitelist; limit/offset are
bounded ints. Objects are schema-qualified with the Gold schema.
"""

from __future__ import annotations

from . import config

_S = config.GOLD_SCHEMA

# Whitelisted sort -> ORDER BY. `priority` (Gold ranking) is the default.
SORTS: dict[str, str] = {
    "priority": "c.priority_score desc nulls last, c.event_date desc nulls last",
    "recent": "c.event_date desc nulls last, c.priority_score desc nulls last",
    "confidence": "c.confidence desc nulls last, c.priority_score desc nulls last",
}

_SELECT = f"""
select
  c.opportunity_id       as signal_id,
  c.state,
  c.relevance_direction,
  c.signal_type,
  c.event_date,
  c.event_date           as published_date,
  d.summary,
  d.why_it_matters       as why_go,
  d.recommended_action,
  ct.quote,
  c.confidence,
  c.priority_score,
  ct.source_url          as url,
  coalesce(ct.source_name, c.source_name) as source,
  d.source_type,
  d.affected_populations,
  c.issue_label,
  c.place_name,
  p.level                as place_level
from {_S}.opportunity_cards c
left join {_S}.opportunity_details d using (opportunity_id)
left join {_S}.opportunity_citations ct
       on ct.opportunity_id = c.opportunity_id and ct.is_primary
left join {_S}.dim_places p on p.place_id = c.place_id
"""


def one_opportunity_query() -> str:
    """SQL for a single opportunity (card + details) by id — for grounding."""
    return f"{_SELECT}where c.opportunity_id = %(id)s limit 1"


CITATIONS_QUERY = f"""
select quote, source_name, source_url, is_primary
from {_S}.opportunity_citations
where opportunity_id = %(id)s
order by is_primary desc, citation_id
"""


def build_signals_query(
    *,
    state: str | None = None,
    direction: str | None = None,
    issue: str | None = None,
    signal_type: str | None = None,
    min_confidence: float | None = None,
    search: str | None = None,
    sort: str = "priority",
    limit: int = 60,
    offset: int = 0,
) -> tuple[str, dict]:
    """Return (sql, parameters) for the filtered opportunity feed."""
    clauses: list[str] = []
    params: dict = {}

    if state:
        clauses.append("c.state = %(state)s")
        params["state"] = state
    if direction:
        clauses.append("c.relevance_direction = %(direction)s")
        params["direction"] = direction
    if signal_type:
        clauses.append("c.signal_type = %(signal_type)s")
        params["signal_type"] = signal_type
    if issue:
        clauses.append("c.issue_label = %(issue)s")
        params["issue"] = issue
    if min_confidence is not None:
        clauses.append("c.confidence >= %(min_confidence)s")
        params["min_confidence"] = float(min_confidence)
    if search:
        clauses.append(
            "(d.summary ilike %(q)s or d.why_it_matters ilike %(q)s "
            "or ct.quote ilike %(q)s or c.issue_label ilike %(q)s "
            "or c.place_name ilike %(q)s)"
        )
        params["q"] = f"%{search}%"

    where = f"where {' and '.join(clauses)}" if clauses else ""
    order_by = SORTS.get(sort, SORTS["priority"])
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    sql = f"{_SELECT}{where}\norder by {order_by}\nlimit {limit} offset {offset}"
    return sql, params


# --- Filter options -----------------------------------------------------------

FILTERS_QUERY = f"""
select 'state' as kind, state as value, count(*)::int as n
  from {_S}.opportunity_cards where state is not null group by state
union all
select 'direction', relevance_direction, count(*)::int
  from {_S}.opportunity_cards where relevance_direction is not null group by relevance_direction
union all
select 'signal_type', signal_type, count(*)::int
  from {_S}.opportunity_cards where signal_type is not null group by signal_type
union all
select 'issue', label, 0 from {_S}.dim_issues
order by kind, n desc, value
"""

# --- Overview aggregates ------------------------------------------------------

HOTSPOT_QUERY = f"""
select issue_label as issue, state,
       count(*)::int as n,
       sum(case when relevance_direction = 'opportunity' then 1 else 0 end)::int as opportunities,
       sum(case when relevance_direction = 'risk' then 1 else 0 end)::int as risks,
       sum(case when relevance_direction = 'watch' then 1 else 0 end)::int as watch,
       max(event_date) as latest
from {_S}.opportunity_cards
where state in ('NY','CA','VA')
group by issue_label, state
"""

SUMMARY_QUERY = f"""
select
  count(*)::int as total,
  sum(case when relevance_direction = 'opportunity' then 1 else 0 end)::int as opportunities,
  sum(case when relevance_direction = 'risk' then 1 else 0 end)::int as risks,
  sum(case when relevance_direction = 'watch' then 1 else 0 end)::int as watch,
  count(distinct state)::int as states,
  max(event_date) as latest
from {_S}.opportunity_cards
"""
