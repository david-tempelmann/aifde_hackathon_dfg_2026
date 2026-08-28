"""LLM event clustering for the silver layer.

One real-world event scraped from several documents produces several near-duplicate
signals (a San Diego heat warning from 6 NWS feeds → 6 `emergency/risk` signals).
This groups them into a single **event** so the graph shows one node and duplicate
scraping becomes a corroboration count.

Same split of responsibilities as :mod:`go_opps.canonicalize`: the **LLM decides
membership** (which signals describe the same event — judgment it's good at, given each
signal's title + location + date), and **we assign the id deterministically** (a hash of
the model's canonical event label), so ids stay stable across full-reprocess runs and
nothing is silently dropped.

We deliberately feed the model *title + location + date + type* and let it use date as
**guidance, not a hard rule** — so it can merge the same event reported across adjacent
days while keeping genuinely different-date instances apart. That flexibility is the whole
reason for an LLM here over a rigid deterministic key.
"""

from __future__ import annotations

import json

from .resolution import _hash12, _norm

# Reasoning-heavy grouping over short descriptors, one batch call — a strong model is
# cheap here. Swappable via the notebook widget.
DEFAULT_EVENT_MODEL = "databricks-claude-sonnet-4-5"

_EVENT_ID_PREFIX = "evt_"


def build_instruction() -> str:
    """Instruction for clustering signals into real-world events."""
    return (
        "You are grouping extracted civic / legislative SIGNALS that were scraped from "
        "public web documents about US state legislation and child/family welfare. Each "
        "item is one signal with a `title` (its source document's headline), a `location`, "
        "a `date`, and a `type`.\n\n"
        "GROUP the ids that describe the SAME real-world event — the same happening "
        "reported by multiple sources or scraped multiple times (e.g. one heat warning, one "
        "committee hearing, one funding announcement). Use `title` and `location` as the "
        "primary evidence.\n\n"
        "Keep genuinely DIFFERENT events apart even when they look similar: two heat "
        "warnings on different dates, or two different bills, are different events. Treat "
        "`date` as guidance, not a strict rule — the same event may be reported across "
        "adjacent days — but do not merge events that are clearly weeks apart. A signal that "
        "stands alone is its own group of one.\n\n"
        "For each group return a short `canonical_label` naming the event and its place "
        "(e.g. 'Extreme Heat Warning — San Diego County'), the `member_ids`, and a 0-1 "
        "`confidence`. Every input id must appear in exactly one group."
    )


def build_payload(items: list[dict]) -> str:
    """Serialize signal descriptors into the JSON the prompt appends.

    Each item is a dict with at least ``id``, ``title``, ``location``, ``date``, ``type``.
    """
    return json.dumps(
        [
            {
                "id": it["id"],
                "title": it.get("title", ""),
                "location": it.get("location", ""),
                "date": it.get("date", ""),
                "type": it.get("type", ""),
            }
            for it in items
        ]
    )


def response_schema() -> dict:
    """Strict ``json_schema`` for the clustering response."""
    return {
        "type": "object",
        "properties": {
            "clusters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "canonical_label": {"type": "string"},
                        "member_ids": {"type": "array", "items": {"type": "integer"}},
                        "confidence": {"type": "number"},
                    },
                    "required": ["canonical_label", "member_ids", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["clusters"],
        "additionalProperties": False,
    }


def response_format_json() -> str:
    """The ``responseFormat`` string ai_query expects."""
    return json.dumps(
        {
            "type": "json_schema",
            "json_schema": {"name": "event_clusters", "strict": True, "schema": response_schema()},
        }
    )


def assign_event_ids(clusters: list[dict], items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn model clusters into deterministic event ids, losing no signal.

    Returns ``(event_rows, signal_event_rows)``:

    - ``event_rows``:        {event_id, canonical_label, match_method, match_confidence}
    - ``signal_event_rows``: {signal_id, event_id}  — every input signal, exactly once.

    ``event_id = 'evt_' + hash12(norm(canonical_label))`` — ours, never the model's. Any
    signal the model failed to place (dropped id, out-of-range, or duplicate assignment)
    falls back to its own singleton event keyed off its signal_id, marked ``llm_unassigned``.
    """
    by_id = {it["id"]: it for it in items}
    seen: set[int] = set()
    events: dict[str, dict] = {}
    signal_event: list[dict] = []

    def _register(event_id: str, label: str, method: str, conf: float | None) -> None:
        cur = events.get(event_id)
        if cur is None:
            events[event_id] = {
                "event_id": event_id, "canonical_label": label,
                "match_method": method, "match_confidence": conf,
            }
        elif method == "llm" and cur["match_method"] != "llm":
            events[event_id] = {**cur, "canonical_label": label, "match_method": "llm",
                                "match_confidence": conf}

    for cl in clusters or []:
        label = (cl.get("canonical_label") or "").strip()
        key = _norm(label)
        if not key:
            continue
        event_id = f"{_EVENT_ID_PREFIX}{_hash12(key)}"
        members = [m for m in (cl.get("member_ids") or []) if m in by_id and m not in seen]
        if not members:
            continue
        _register(event_id, label, "llm", cl.get("confidence"))
        for m in members:
            seen.add(m)
            signal_event.append({"signal_id": by_id[m]["signal_id"], "event_id": event_id})

    # Fallback: any signal the model didn't place → its own singleton event (never dropped).
    for idx, it in by_id.items():
        if idx in seen:
            continue
        event_id = f"{_EVENT_ID_PREFIX}{_hash12(it['signal_id'])}"
        _register(event_id, (it.get("title") or "").strip(), "llm_unassigned", None)
        signal_event.append({"signal_id": it["signal_id"], "event_id": event_id})

    return list(events.values()), signal_event
