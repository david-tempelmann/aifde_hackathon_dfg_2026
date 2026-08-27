"""Single-pass extraction contract for the silver layer.

One ``ai_query`` call per chunk produces a fully-grounded signal record:
classification (type + direction), a controlled issue label, a summary, the
mentioned geography/orgs/policies, and the *verbatim* supporting quote that all
of the above must be anchored to. Grounding + relevance + classification in one
pass keeps a single prompt to maintain; the content is small enough that the
per-call cost is fine.

Everything the SQL extraction step needs lives here: the mission-aware
instruction (the relevance gate), the JSON response schema, and the default
model. Kept out of the notebook so the contract is versioned with the wheel.
"""

from __future__ import annotations

import json

from .vocab import ISSUE_LABELS, PLACE_LEVELS, RELEVANCE_DIRECTIONS, SIGNAL_TYPES

# Default extraction model. Swappable via the notebook ``model`` widget.
# Claude is a strong instruction-follower for grounded, schema-constrained
# extraction (verbatim quotes), and haiku is fast/cheap for batch.
DEFAULT_MODEL = "databricks-claude-haiku-4-5"

# Signals below this confidence are kept in the landing table but filtered out
# of the curated ``silver.signals`` table (surfaced/flagged decisions live in
# gold). Overridable via widget.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# How much of each chunk to hand the model (defensive cap; chunks are already
# bounded by the chunker, this just protects against a pathological row).
MAX_INPUT_CHARS = 12000

# --------------------------------------------------------------------------
# The instruction. This IS the relevance gate — it defines who GO is so the
# model can distinguish a genuine child/family signal from generic civic news.
# --------------------------------------------------------------------------
INSTRUCTION = (
    "You are an analyst for the Global Orphan (GO) Project, a nonprofit serving "
    "vulnerable children and families. Its CarePortal platform connects local "
    "community and church partners to meet the concrete needs of children in "
    "crisis and families involved with the child-welfare/foster-care system.\n\n"
    "You are given one scraped public web item (title + text) — often state or "
    "local legislative activity, sometimes news, government notices, or social "
    "posts. Extract exactly ONE primary signal: an atomic 'something is "
    "happening' that a GO State Director could act on.\n\n"
    "Judge GO-relevance strictly. It is relevant only if it plausibly bears on "
    "children, families, foster care/child welfare, or the concrete needs GO "
    "and CarePortal address (housing, food, healthcare, youth mental health, "
    "education, economic support, disaster impact on families). Generic "
    "business, sports, politics, or adult-only items are NOT relevant — set "
    "is_go_relevant=false for those.\n\n"
    "Set relevance_direction from GO's perspective:\n"
    "- 'opportunity' — an opening to recruit CarePortal partners or build momentum;\n"
    "- 'risk' — something that could adversely affect GO/CarePortal (e.g. a new "
    "reporting mandate or funding cut);\n"
    "- 'watch' — relevant context, not yet actionable.\n\n"
    "Grounding is mandatory: supporting_quote MUST be copied verbatim from the "
    "provided text (an exact substring), and every other field must be "
    "supported by that text. Do not invent facts, dates, places, or "
    "organizations. If the text is too thin to support a field, leave it empty "
    "(empty string or empty array). confidence is your 0-1 certainty that this "
    "is a real, correctly-classified, GO-relevant signal."
)


def response_schema() -> dict:
    """OpenAI-style ``json_schema`` for ai_query structured output (strict).

    Strict mode requires every property to be listed in ``required`` and
    ``additionalProperties: false``. 'Optional' fields are modelled as
    always-present but allowed-empty (empty string / empty array).
    """
    place_item = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Place name as written in the text."},
            "level": {"type": "string", "enum": PLACE_LEVELS},
            "state": {
                "type": "string",
                "description": "Two-letter state (NY/CA/VA/US) if determinable, else empty.",
            },
        },
        "required": ["name", "level", "state"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "is_go_relevant": {"type": "boolean"},
            "signal_type": {"type": "string", "enum": SIGNAL_TYPES},
            "relevance_direction": {"type": "string", "enum": RELEVANCE_DIRECTIONS},
            # One or more controlled issue labels → feeds the signal_issues bridge.
            "issue_labels": {
                "type": "array",
                "items": {"type": "string", "enum": ISSUE_LABELS},
                "description": "GO issue category(ies), most relevant first.",
            },
            "summary": {"type": "string", "description": "One or two sentence neutral summary."},
            "affected_populations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Groups affected, e.g. 'foster youth', 'low-income families'.",
            },
            "places": {"type": "array", "items": place_item},
            "organizations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Agencies, committees, sponsors, nonprofits named (Could-have NER).",
            },
            "policies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Named bills/policies referenced, e.g. 'SB 1234' (Could-have NER).",
            },
            "event_date": {
                "type": "string",
                "description": "ISO date (YYYY-MM-DD) of the event if stated, else empty.",
            },
            "supporting_quote": {
                "type": "string",
                "description": "Verbatim substring of the source text that grounds this signal.",
            },
            "why_go": {
                "type": "string",
                "description": "One line: why this matters to GO / CarePortal.",
            },
            "confidence": {"type": "number"},
        },
        "required": [
            "is_go_relevant",
            "signal_type",
            "relevance_direction",
            "issue_labels",
            "summary",
            "affected_populations",
            "places",
            "organizations",
            "policies",
            "event_date",
            "supporting_quote",
            "why_go",
            "confidence",
        ],
        "additionalProperties": False,
    }


def response_format_json() -> str:
    """The ``responseFormat`` string ai_query expects (a JSON-encoded object)."""
    return json.dumps(
        {
            "type": "json_schema",
            "json_schema": {
                "name": "go_signal",
                "strict": True,
                "schema": response_schema(),
            },
        }
    )
