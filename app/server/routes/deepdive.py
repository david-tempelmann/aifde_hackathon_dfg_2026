"""Topic Deep-Dive endpoint — Genie findings for a Hot-Issue card.

Calls the certified Genie space live (see server.genie) and caches the result
per topic+region so repeat opens are instant. Genie can take ~20-40s on a cold
call, so the frontend shows a loading state; a TTL cache keeps warm topics fast.
"""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException, Query

from .. import genie

router = APIRouter()

# Fixed topic taxonomy + regions (mirror the Genie notebook widgets).
TOPICS = [
    "Housing stability & homelessness",
    "Poverty & economic support",
    "Education access",
    "Family preservation & foster care",
    "Child welfare & protection",
    "Youth mental health",
    "Healthcare access",
    "Emergency & disaster response",
    "Food & material needs",
]
REGIONS = ["All", "CA", "NY", "VA"]

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 1800.0  # findings don't change fast; refresh=true forces a rerun


@router.get("/deepdive/options")
def deepdive_options():
    """Topic + region choices for the page selectors."""
    return {"topics": TOPICS, "regions": REGIONS}


@router.get("/deepdive")
def deepdive(
    topic: str = Query(...),
    region: str = Query("All"),
    signal_count: str | None = Query(default=None),
    signal_mix: str | None = Query(default=None),
    sources: str | None = Query(default=None),
    key_dates: str | None = Query(default=None),
    latest: str | None = Query(default=None),
    refresh: bool = Query(default=False),
):
    """Genie deep-dive findings for a topic+region (cached; ?refresh=true reruns)."""
    key = f"{topic}|{region}"
    now = time.monotonic()
    if not refresh:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and now - hit[0] < _CACHE_TTL_SECONDS:
                return {**hit[1], "cached": True}

    card = {
        "signal_count": signal_count,
        "signal_mix": signal_mix,
        "sources": sources,
        "key_dates": key_dates,
        "latest": latest,
    }
    try:
        payload = genie.deep_dive(topic, region, card)
    except Exception as exc:  # network / auth / Genie API error
        raise HTTPException(status_code=502, detail=f"Genie deep-dive failed: {exc}")

    if payload.get("genie_status") != "COMPLETED":
        raise HTTPException(
            status_code=502,
            detail=f"Genie returned status {payload.get('genie_status')!r} — no findings.",
        )

    with _CACHE_LOCK:
        _CACHE[key] = (now, payload)
    return {**payload, "cached": False}
