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

from .vocab import (
    ISSUE_LABELS,
    ISSUE_TAXONOMY,
    PLACE_LEVELS,
    RELEVANCE_DIRECTIONS,
    SIGNAL_TYPE_DEFS,
    SIGNAL_TYPES,
)


def _glossary(defs: list[dict], key: str) -> str:
    """Render '- <key>: <description>' lines. Prompt glossaries are generated from
    the same vocab lists that build the schema enums, so they can never drift."""
    return "\n".join(f"- {d[key]}: {d['description']}" for d in defs)


_SIGNAL_TYPE_GLOSSARY = _glossary(SIGNAL_TYPE_DEFS, "type")
_ISSUE_GLOSSARY = _glossary(ISSUE_TAXONOMY, "label")

# Default extraction model. Swappable via the notebook ``model`` widget.
# Claude is a strong instruction-follower for grounded, schema-constrained
# extraction (verbatim quotes), and haiku is fast/cheap for batch.
DEFAULT_MODEL = "databricks-claude-haiku-4-5"

# Signals below this confidence are kept in the landing table but filtered out
# of the curated ``silver.signals`` table (surfaced/flagged decisions live in
# gold). Overridable via widget.
DEFAULT_CONFIDENCE_THRESHOLD = 0.4

# How much of each chunk to hand the model (defensive cap; chunks are already
# bounded by the chunker, this just protects against a pathological row).
MAX_INPUT_CHARS = 12000

# --------------------------------------------------------------------------
# The instruction. This IS the relevance gate — it defines who GO is so the
# model can distinguish a genuine child/family signal from generic civic news.
# --------------------------------------------------------------------------
INSTRUCTION = (
    # --- Context ---
    "You are an analyst for the Global Orphan (GO) Project, a U.S.-focused nonprofit "
    "serving vulnerable children and families. Its CarePortal platform connects local "
    "community and church partners with concrete needs involving children in crisis and "
    "families connected to the child-welfare and foster-care systems.\n\n"
    "You are given one scraped public web item (title + text) — state or local legislation, "
    "government activity, news, notices, reports, programs, funding, emergencies, or social "
    "posts. Extract exactly ONE primary signal: one atomic, source-supported statement "
    "describing something that is happening or has happened and that could matter to a GO "
    "State Director.\n\n"
    # --- GO relevance (the gate) ---
    "Judge GO-relevance strictly. An item is relevant only if it plausibly concerns "
    "children/adolescents; parents, caregivers, or families; foster care, kinship care, "
    "adoption, reunification, or child welfare; housing stability or homelessness; food or "
    "material needs; healthcare access; youth mental health; education access or school "
    "support; poverty, income support, childcare cost, or family economic stability; or "
    "emergencies/disasters affecting children or families. Generic business, sports, "
    "elections, or adult-only content is NOT relevant unless the text establishes a clear "
    "connection to the above. Do not force a classification merely because the source is "
    "governmental or political. If the item is not GO-relevant, set is_go_relevant=false, "
    "signal_type='other', relevance_direction='watch', issue_labels=[], and leave "
    "GO-specific fields empty unless directly supported.\n\n"
    # --- Signal selection ---
    "Select the primary event, action, development, or condition — not a broad topic or "
    "background. Prefer a signal that is specific (not generic), recent or clearly dated when "
    "a date is given, and actionable for a GO State Director. If the item contains several "
    "developments, pick the single most GO-relevant one; do NOT combine separate developments "
    "into one signal.\n\n"
    # --- Relevance direction ---
    "Set relevance_direction from GO's perspective:\n"
    "- opportunity: may create an opening to recruit CarePortal partners, expand services, "
    "coordinate a response, secure resources, or build momentum on a GO-relevant issue.\n"
    "- risk: may negatively affect children, families, child-welfare systems, CarePortal, or "
    "GO's ability to respond (funding cuts, service reductions, new burdensome requirements, "
    "worsening conditions, increased unmet need).\n"
    "- watch: relevant but not yet clearly an opportunity or risk. Do not label opportunity or "
    "risk unless the text supports it.\n\n"
    # --- Signal type glossary (generated from the controlled vocabulary) ---
    "Assign exactly one signal_type:\n" + _SIGNAL_TYPE_GLOSSARY + "\n\n"
    # --- Issue glossary (generated from the controlled taxonomy) ---
    "Assign one or more issue_labels, most relevant first:\n" + _ISSUE_GLOSSARY + "\n\n"
    # --- Grounding ---
    "Grounding is mandatory. supporting_quote MUST be copied verbatim from the provided title "
    "or text (an exact substring, including wording and punctuation) and must directly support "
    "the signal. Every populated field must be supported by the input — do not use outside "
    "knowledge, assumptions, or likely implications, and do not invent facts, dates, places, "
    "organizations, policies, populations, or GO impacts. If a field is not explicitly "
    "supported, use an empty string or empty array. The summary must describe what the source "
    "says, not what may happen; why_go may state the GO relevance but must stay grounded and "
    "not claim an impact the source does not establish.\n\n"
    # --- Confidence (two axes) ---
    "Report two scores, each between 0 and 1:\n"
    "- source_confidence: how much the source and its supporting_quote let us TRUST the signal. "
    "Is the source credible (an official/government notice or established news outlet warrants "
    "more trust than an anonymous social post or promotional/speculative text), and does the "
    "verbatim quote directly and unambiguously support the extracted claim? Low when the source "
    "is weak, the quote is thin or off-point, or the signal leans on implication. The item's "
    "SOURCE and SOURCE TYPE are provided with the input — factor them in.\n"
    "- overall_confidence: your overall certainty that this is a real, correctly-extracted, "
    "GO-relevant signal. Do not raise it merely because the topic is generally relevant to GO."
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
            "level": {
                "type": "string",
                "enum": PLACE_LEVELS,
                "description": "Granularity: 'place' = a city/town/village.",
            },
            "state": {
                "type": "string",
                "description": "Two-letter USPS state code (e.g. CA, TX, NY), or US for national scope, if determinable, else empty.",
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
            # Two confidence axes (0-1). overall_confidence is the pipeline anchor
            # (drives the gate + ranking); source_confidence is a trust diagnostic.
            "source_confidence": {
                "type": "number",
                "description": "Source credibility + how well the quote supports the signal.",
            },
            "overall_confidence": {
                "type": "number",
                "description": "Overall certainty this is a real, GO-relevant, correctly-extracted signal.",
            },
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
            "source_confidence",
            "overall_confidence",
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
