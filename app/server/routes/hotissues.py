"""Hot Issues — heat-ranked issue x place hotspots + KG mini sub-graph.

Aggregates the in-territory opportunity signals into (issue, place) hotspots,
ranks them by a transparent heat score, and returns the top N with their
underlying signals — each carrying its 1-hop knowledge-graph neighbourhood
(concerns / affects / involves / references) read from the synced graph tables.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Query

from .. import db, queries

router = APIRouter()

# Signal-type impact weight (mirrors the Gold ranking); heat blends this with
# volume, recency and source corroboration so every component is explainable.
_TODAY = datetime.date.today()


def _to_date(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _recency(d: datetime.date | None) -> float:
    if d is None:
        return 0.0
    return max(0.0, 1.0 - min(abs((d - _TODAY).days), 90) / 90.0)


@router.get("/hotissues")
def hot_issues(limit: int = Query(default=4, ge=1, le=12)):
    """Top heat-ranked hotspots (issue x place) with signals + KG sub-graphs."""
    sql, params = queries.hot_signals_query()
    rows = db.query(sql, params)

    # Group signals into (issue, place) hotspots.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if not r.get("issue_label") or not r.get("place_name"):
            continue
        groups[(r["issue_label"], r["place_name"], r["state"], r.get("place_level"))].append(r)

    max_n = max((len(v) for v in groups.values()), default=1)
    cards = []
    for (issue, place, state, level), sigs in groups.items():
        if len(sigs) < 2:  # a hotspot is a cluster, not a lone signal
            continue
        n = len(sigs)
        n_opp = sum(1 for s in sigs if s["relevance_direction"] == "opportunity")
        n_risk = sum(1 for s in sigs if s["relevance_direction"] == "risk")
        n_watch = sum(1 for s in sigs if s["relevance_direction"] == "watch")
        sources = sorted({s["source"] for s in sigs if s.get("source")})
        priority_c = max((s.get("priority_score") or 0.0) for s in sigs)
        recency_c = max((_recency(_to_date(s.get("event_date"))) for s in sigs), default=0.0)
        volume_c = n / max_n
        corrob_c = min(len(sources) / 3, 1.0)
        heat = round(100 * (0.35 * priority_c + 0.30 * volume_c + 0.20 * recency_c + 0.15 * corrob_c))
        past = [d for d in (_to_date(s.get("event_date")) for s in sigs) if d and d <= _TODAY]
        upc = [d for d in (_to_date(s.get("event_date")) for s in sigs) if d and d > _TODAY]
        dom = max([("opportunity", n_opp), ("risk", n_risk), ("watch", n_watch)], key=lambda x: x[1])[0]
        sigs_sorted = sorted(sigs, key=lambda s: (s.get("priority_score") or 0.0), reverse=True)
        cards.append({
            "issue": issue, "place": place, "state": state, "level": level or "unresolved",
            "n": n, "n_opp": n_opp, "n_risk": n_risk, "n_watch": n_watch,
            "sources": sources, "heat": heat, "top_priority": round(100 * priority_c),
            "latest": max(past).isoformat() if past else None,
            "nextup": min(upc).isoformat() if upc else None,
            "dom": dom,
            "components": {
                "priority": round(priority_c, 2), "volume": round(volume_c, 2),
                "recency": round(recency_c, 2), "corroboration": round(corrob_c, 2),
            },
            "signals": [{
                "signal_id": s["signal_id"], "summary": s.get("summary"),
                "dir": s["relevance_direction"], "date": s.get("event_date"),
                "type": s.get("signal_type"), "source": s.get("source"),
                "url": s.get("url"), "why_go": s.get("why_go"), "edges": [],
            } for s in sigs_sorted],
        })

    cards.sort(key=lambda c: c["heat"], reverse=True)
    top = cards[:limit]
    for i, c in enumerate(top, 1):
        c["rank"] = i

    # Attach each signal's 1-hop KG neighbourhood.
    sig_index = {s["signal_id"]: s for c in top for s in c["signals"]}
    if sig_index:
        ids = [f"sig_{sid}" for sid in sig_index]
        try:
            edge_rows = db.query(queries.GRAPH_EDGES_FOR_SIGNALS, {"ids": ids})
        except Exception as exc:  # graph tables not synced yet — degrade to no sub-graphs
            print("[hotissues] KG edges unavailable:", exc)
            edge_rows = []
        by_sig: dict[str, list[dict]] = defaultdict(list)
        for e in edge_rows:
            by_sig[e["src_id"]].append({
                "predicate": e["predicate"], "dst_type": e["dst_type"],
                "dst_label": e["dst_label"],
                "conf": float(e["confidence"]) if e.get("confidence") is not None else 0.0,
            })
        for sid, s in sig_index.items():
            s["edges"] = by_sig.get(f"sig_{sid}", [])

    return {"count": len(top), "cards": top}
