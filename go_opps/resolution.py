"""Deterministic normalization helpers for the silver layer.

Open-ended **organization / policy** entity resolution moved to LLM
canonicalization (:mod:`go_opps.canonicalize`) — clustering surface variants is
judgment work an LLM does far better than a hand-kept alias seed, and it needs no
per-entity maintenance. What stays here is the deterministic, rule-based piece
that belongs in code: the shared string primitives, and **place-name**
canonicalization, used by both stage 04 and the gazetteer alias build
(``notebooks/reference/00_gazetteer.py``) so extracted names join to FIPS.

All matching here is deterministic (exact / structural), so ids are stable across
the full-reprocess pipeline.
"""

from __future__ import annotations

import hashlib
import re


def _hash12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _norm(s: str) -> str:
    """Lowercase, drop dots (so 'U.S.'->'us', 'A.B.'->'ab'), strip remaining
    punctuation to single spaces, collapse, trim."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace(".", "")).strip()


# ==========================================================================
# Places — normalization shared with the gazetteer alias build
# ==========================================================================

# tokens stripped so "City of San Diego" / "San Diego County" -> "san diego"
_PLACE_STRIP_RE = re.compile(
    r"(?i)\b(city and county of|city of|town of|village of|borough of|county of|the|county|city|town|village|borough|parish|municipality)\b"
)


def normalize_place_name(name: str) -> str:
    """Canonical key for place matching. MUST mirror the SQL in stage 04."""
    s = _PLACE_STRIP_RE.sub(" ", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
