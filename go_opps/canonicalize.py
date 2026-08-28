"""LLM batch canonicalization for open-ended entities (orgs / policies).

The deterministic resolver in :mod:`go_opps.resolution` handles the closed,
structural cases well (bill numbers, a hand-kept alias seed, parenthetical
acronyms). It cannot keep up with the open-ended long tail — "CA Dept. of Social
Services" vs "California Department of Social Services" vs "the Department" — and
adding rules for each is a losing game.

This module applies the LLM where it is actually strong (**judgment**: deciding
which surface strings name the same real-world entity) while keeping the part it
must never own (**ID assignment**: the canonical id) deterministic. The flow:

1. Collect the *distinct* surface strings across the corpus (a small set — far
   smaller than the chunk count, so this is one cheap batch, not a per-row call).
2. One ``ai_query`` clusters them into canonical entities (see :func:`response_format_json`).
3. We assign each cluster a **stable hashed id from its canonical name** — the id
   comes from us, never from the model — and fall back to a per-surface id for
   anything the model dropped, so no surface is ever lost.

Keeping ids a pure function of the (normalized) canonical name means they stay
stable run-to-run as long as the model names an entity consistently, preserving
the deterministic-key / incremental-MERGE story (solution-design §6).
"""

from __future__ import annotations

import json
import re

from .resolution import _hash12, _norm

# A stronger model is worth it here: clustering/linking is reasoning-heavy and it
# is a single batch call, so cost is negligible. Swappable via the notebook widget.
DEFAULT_CANON_MODEL = "databricks-claude-sonnet-4-5"

# Entity-type label sets, surfaced on the dimension for the graph/app to filter on.
ORG_TYPES = [
    "government_agency", "legislative_body", "court", "nonprofit",
    "company", "coalition", "other",
]
POLICY_TYPES = ["bill", "law", "program", "regulation", "court_case", "other"]

_KIND = {
    "organizations": {
        "id_prefix": "org_",
        "entity_types": ORG_TYPES,
        "noun": "organizations (agencies, legislative committees, courts, nonprofits, companies)",
        "canonical_rule": (
            "Use the full official name, keeping a well-known acronym in parentheses, "
            "e.g. 'California Department of Health Care Services (DHCS)'. Bind a "
            "standalone acronym ('DHCS') to the full name when both appear."
        ),
        # Orgs rarely carry instrument numbers; the guard would only add false splits.
        "guard_instrument_numbers": False,
    },
    "policies": {
        "id_prefix": "pol_",
        "entity_types": POLICY_TYPES,
        "noun": "policies (bills, laws, programs, regulations, court cases)",
        "canonical_rule": (
            "For a bill, use its normalized code plus short title, e.g. 'AB 2376'. "
            "For a named program, use its official name with acronym, e.g. "
            "'Supplemental Nutrition Assistance Program (SNAP)'. Treat the same bill "
            "written differently ('A.B. 2376 (Bains)', 'AB 2376') as one entity."
        ),
        # A bill/ordinance/resolution NUMBER is a hard identity key — enforce it.
        "guard_instrument_numbers": True,
    },
}


# --------------------------------------------------------------------------
# Numbered-instrument guard (structural, no alias list).
#
# A bill/ordinance/resolution number is a hard identity key: two surfaces with
# DIFFERENT numbers are DIFFERENT instruments, however similar their text. The
# LLM occasionally fuses them (e.g. 'ORD. 2026-190' with 'ORD. 2026-191'), so we
# split any cluster that carries more than one distinct number. This is pure
# structure — it never merges anything, only refuses a bad merge — and is inert
# on any surface without such a number.
# --------------------------------------------------------------------------
_INSTRUMENT_RE = re.compile(
    r"(?i)\b("
    r"s\.?b|a\.?b|h\.?b|h\.?r|s\.?c\.?r|a\.?c\.?r|s\.?j\.?r|h\.?j\.?r|s\.?r"  # bill chambers
    r"|ordinance|resolution|ord|res|sb|ab|hb|hr|sr|a|s|h"                    # + short forms
    r")\.?\s*(?:no\.?\s*)?(\d{1,5}(?:-\d{1,5})?)\b"                          # optional 'No.' + number(-seq)
)
_PREFIX_SYNONYM = {"ordinance": "ord", "resolution": "res"}


def instrument_number(surface: str) -> str | None:
    """Normalized numbered-instrument key, or None.

    'AB 2376' / 'A.B. 2376 (Bains)' -> 'ab:2376'; 'ORD. 2026-190' -> 'ord:2026-190'.
    Prefix is kept so same-number different-chamber bills ('SB 100' vs 'AB 100') stay
    distinct; a surface with no such number returns None (guard does nothing).
    """
    m = _INSTRUMENT_RE.search(surface or "")
    if not m:
        return None
    prefix = m.group(1).lower().replace(".", "")
    prefix = _PREFIX_SYNONYM.get(prefix, prefix)
    return f"{prefix}:{m.group(2)}"


def _split_by_instrument(clusters: list[dict], by_id: dict[int, tuple[str, int]]) -> list[dict]:
    """Split any cluster whose members carry >1 distinct instrument number.

    Members are regrouped by number (surfaces with no number form their own group,
    kept together); each group becomes its own cluster, its canonical name the most
    frequent surface in the group. Clusters with 0 or 1 distinct number pass through.
    """
    out: list[dict] = []
    for cl in clusters or []:
        members = [m for m in (cl.get("member_ids") or []) if m in by_id]
        if not members:
            out.append(cl)
            continue
        groups: dict[str | None, list[int]] = {}
        for m in members:
            groups.setdefault(instrument_number(by_id[m][0]), []).append(m)
        if len([k for k in groups if k is not None]) <= 1:
            out.append(cl)
            continue
        for ids in groups.values():
            rep = max(ids, key=lambda i: (by_id[i][1], len(by_id[i][0]), by_id[i][0]))
            out.append({
                "canonical_name": by_id[rep][0],
                "entity_type": cl.get("entity_type", "other"),
                "member_ids": ids,
                "confidence": cl.get("confidence"),
            })
    return out


def build_instruction(kind: str) -> str:
    """The clustering instruction for a given entity ``kind``."""
    k = _KIND[kind]
    return (
        f"You are canonicalizing a list of {k['noun']} that were extracted from "
        "public web documents about US state legislation and child/family welfare.\n\n"
        "Each input item has an integer `id`, the extracted surface `name`, and the "
        "`count` of documents it appeared in. GROUP the ids that refer to the SAME "
        "real-world entity (merge acronyms, abbreviations, punctuation/spelling "
        "variants, and 'the Department'-style short forms with their full name).\n\n"
        "Keep genuinely DIFFERENT entities apart — do not merge two different "
        "agencies just because their names are similar. If an item is too generic to "
        "identify (e.g. a bare 'the agency'), put it in its own group.\n\n"
        f"For each group return: `canonical_name` — {k['canonical_rule']} — an "
        f"`entity_type` from the allowed set, the `member_ids` in the group, and a "
        "0-1 `confidence` in the grouping. Every input id must appear in exactly one "
        "group."
    )


def build_payload(items: list[tuple[int, str, int]]) -> str:
    """Serialize ``(id, surface, count)`` rows into the JSON the prompt appends."""
    return json.dumps([{"id": i, "name": name, "count": cnt} for i, name, cnt in items])


def response_schema(kind: str) -> dict:
    """Strict ``json_schema`` for the clustering response."""
    return {
        "type": "object",
        "properties": {
            "clusters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "canonical_name": {"type": "string"},
                        "entity_type": {"type": "string", "enum": _KIND[kind]["entity_types"]},
                        "member_ids": {"type": "array", "items": {"type": "integer"}},
                        "confidence": {"type": "number"},
                    },
                    "required": ["canonical_name", "entity_type", "member_ids", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["clusters"],
        "additionalProperties": False,
    }


def response_format_json(kind: str) -> str:
    """The ``responseFormat`` string ai_query expects."""
    return json.dumps(
        {
            "type": "json_schema",
            "json_schema": {"name": "entity_clusters", "strict": True, "schema": response_schema(kind)},
        }
    )


def assign_ids(
    clusters: list[dict],
    items: list[tuple[int, str, int]],
    kind: str,
) -> tuple[list[dict], list[dict]]:
    """Turn model clusters into deterministic ids, losing no surface.

    Returns ``(dim_rows, map_rows)``:

    - ``dim_rows``:  {id, canonical_name, entity_type, match_method, match_confidence}
    - ``map_rows``:  {surface, id}  — every input surface, exactly once.

    The id is ``prefix + hash12(norm(canonical_name))`` — ours, never the model's.
    Any surface the model failed to place (dropped id, out-of-range id, or a
    duplicate assignment) falls back to its own id from its normalized surface,
    marked ``llm_unassigned`` so the gap is auditable.
    """
    prefix = _KIND[kind]["id_prefix"]
    by_id = {i: (name, cnt) for i, name, cnt in items}
    if _KIND[kind].get("guard_instrument_numbers"):
        clusters = _split_by_instrument(clusters, by_id)
    seen: set[int] = set()
    dims: dict[str, dict] = {}
    surface_to_id: dict[str, str] = {}

    def _register(entity_id: str, canonical: str, etype: str, method: str, conf: float | None) -> None:
        cur = dims.get(entity_id)
        if cur is None:
            dims[entity_id] = {
                "id": entity_id, "canonical_name": canonical, "entity_type": etype,
                "match_method": method, "match_confidence": conf,
            }
        elif method == "llm" and cur["match_method"] != "llm":
            # a real cluster beats a fallback singleton on the same id
            dims[entity_id] = {**cur, "canonical_name": canonical, "entity_type": etype,
                               "match_method": "llm", "match_confidence": conf}

    for cl in clusters or []:
        canonical = (cl.get("canonical_name") or "").strip()
        key = _norm(canonical)
        if not key:
            continue
        entity_id = f"{prefix}{_hash12(key)}"
        etype = cl.get("entity_type") or "other"
        conf = cl.get("confidence")
        member_ids = [m for m in (cl.get("member_ids") or []) if m in by_id and m not in seen]
        if not member_ids:
            continue
        _register(entity_id, canonical, etype, "llm", conf)
        for m in member_ids:
            seen.add(m)
            surface_to_id[by_id[m][0]] = entity_id

    # Fallback: any surface the model didn't place gets its own id (never dropped).
    for i, name, _cnt in items:
        if i in seen:
            continue
        key = _norm(name)
        entity_id = f"{prefix}{_hash12(key)}" if key else f"{prefix}{_hash12(name)}"
        _register(entity_id, name.strip(), "other", "llm_unassigned", None)
        surface_to_id[name] = entity_id

    map_rows = [{"surface": s, "id": eid} for s, eid in surface_to_id.items()]
    return list(dims.values()), map_rows
