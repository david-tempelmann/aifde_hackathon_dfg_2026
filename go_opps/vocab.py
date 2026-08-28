"""Controlled vocabularies for the GO Project silver layer.

Keeping these in the package (not inline in notebooks) means the extraction
prompt, the dimension seed tables, and any downstream code all read from a
*single* source of truth. Change a label here and every stage picks it up on
the next wheel build.

The taxonomy is deliberately small and GO-mission-centric: the point of the
controlled set is that ``issue_label`` comes back joinable, not free text.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Issue taxonomy (M) — the GO-relevant controlled label set.
#
# Each issue maps to a stable ``issue_id`` (used as the dimension key so the
# key never changes if we reword a label). ``other`` is the escape hatch so the
# model is never forced to mislabel; rows that land on ``other`` are a signal we
# may be missing a category.
# --------------------------------------------------------------------------
ISSUE_TAXONOMY: list[dict[str, str]] = [
    {
        "issue_id": "child_welfare",
        "label": "Child welfare & protection",
        "description": (
            "Child protective services, mandated reporting, abuse/neglect, "
            "child safety regulation. Directly relevant to CarePortal."
        ),
    },
    {
        "issue_id": "family_preservation",
        "label": "Family preservation & foster care",
        "description": (
            "Foster care, kinship care, adoption, reunification, and services "
            "that keep families together."
        ),
    },
    {
        "issue_id": "housing_stability",
        "label": "Housing stability & homelessness",
        "description": "Housing affordability, eviction, homelessness, shelter.",
    },
    {
        "issue_id": "food_material_needs",
        "label": "Food & material needs",
        "description": "Food security, SNAP/benefits, clothing, and basic material support.",
    },
    {
        "issue_id": "youth_mental_health",
        "label": "Youth mental health",
        "description": "Mental/behavioral health of children and adolescents.",
    },
    {
        "issue_id": "healthcare_access",
        "label": "Healthcare access",
        "description": "Access to medical, dental, and behavioral healthcare for families/children.",
    },
    {
        "issue_id": "education_access",
        "label": "Education access",
        "description": "Early childhood, K-12 access/equity, and school support services.",
    },
    {
        "issue_id": "economic_support",
        "label": "Poverty & economic support",
        "description": "Poverty, income support, childcare cost, and family economic stability.",
    },
    {
        "issue_id": "emergency_response",
        "label": "Emergency & disaster response",
        "description": "Natural disasters, emergencies, and displacement affecting families.",
    },
    {
        "issue_id": "other",
        "label": "Other",
        "description": "GO-relevant but does not fit a category above.",
    },
]

# Convenience lookups.
ISSUE_LABELS: list[str] = [i["label"] for i in ISSUE_TAXONOMY]
ISSUE_LABEL_TO_ID: dict[str, str] = {i["label"]: i["issue_id"] for i in ISSUE_TAXONOMY}

# --------------------------------------------------------------------------
# Signal types — predominantly legislative, per the use case, plus a few
# civic/administrative types the corpus actually contains (programs, funding,
# reports, emergencies).
# --------------------------------------------------------------------------
# Each type carries the definition the model sees (the glossary), so the schema
# enum and the prompt are generated from ONE list and can't drift.
SIGNAL_TYPE_DEFS: list[dict[str, str]] = [
    {"type": "bill_introduced", "description": "A bill or legislative proposal has been formally introduced."},
    {"type": "committee_hearing", "description": "A legislative committee hearing, briefing, or testimony session is scheduled or taking place."},
    {"type": "proposed_mandate", "description": "A proposed requirement, obligation, or standard that organizations, agencies, or individuals would have to follow."},
    {"type": "vote", "description": "A legislative or government vote, or a voting outcome."},
    {"type": "amendment", "description": "A proposed or adopted change to a bill, law, regulation, budget, or policy."},
    {"type": "funding", "description": "A grant, appropriation, budget allocation, funding increase or reduction, or other financial commitment."},
    {"type": "report_indicator", "description": "A report, study, statistic, trend, or metric indicating the scale or direction of an issue."},
    {"type": "program", "description": "The creation, expansion, modification, evaluation, or closure of a government or community program."},
    {"type": "emergency", "description": "An urgent event or response — a disaster, displacement, or sudden disruption affecting children or families."},
    {"type": "other", "description": "A GO-relevant signal that does not fit the categories above."},
]

# Derived enum — values/order unchanged, so response_schema() is untouched.
SIGNAL_TYPES: list[str] = [d["type"] for d in SIGNAL_TYPE_DEFS]

# Direction the signal points for GO / CarePortal.
RELEVANCE_DIRECTIONS: list[str] = ["opportunity", "risk", "watch"]

# Place granularity levels (coarsest → finest). "place" is the Census settlement
# tier (city / town / village / CDP) — it matches the gazetteer `level` and the
# gold locality scoring, so the model's level agrees with what resolution emits.
PLACE_LEVELS: list[str] = ["nation", "state", "county", "place"]

# --------------------------------------------------------------------------
# Gazetteer seed — the territory scope (NY / CA / VA) plus a US national row.
# Extracted finer places (county/place) are resolved/appended against this in
# the signals stage. ``region`` matches the value carried on raw_issues.
# --------------------------------------------------------------------------
STATE_SEED: list[dict[str, str]] = [
    {"place_id": "us", "canonical_name": "United States", "state": "US", "level": "nation"},
    {"place_id": "state_ny", "canonical_name": "New York", "state": "NY", "level": "state"},
    {"place_id": "state_ca", "canonical_name": "California", "state": "CA", "level": "state"},
    {"place_id": "state_va", "canonical_name": "Virginia", "state": "VA", "level": "state"},
]
