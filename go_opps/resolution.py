"""Deterministic entity resolution for the silver layer (no ML).

Collapses surface variants of the same real-world entity to one canonical id:

- **Policies/bills** — normalize bill numbers ("A.B. 2376 (Bains)" -> "AB 2376",
  state-qualified) and map known program names via an alias table (ACA, SNAP, …).
- **Organizations** — an alias seed for common agencies, plus dynamic
  *acronym linking*: a parenthetical acronym ("… Services (DHCS)") binds the
  standalone "DHCS" surface to the same org.
- **Places** — name normalization shared with the gazetteer alias build
  (`notebooks/reference/00_gazetteer.py`), so extracted names join to FIPS.

All matching is deterministic (exact / alias / regex / structural) so ids are
stable across the full-reprocess pipeline. Fuzzy/embedding tiers are a later
phase; anything unmatched gets a stable hashed fallback id + `unresolved`.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

_TERRITORY = {"NY", "CA", "VA"}


def _hash12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _norm(s: str) -> str:
    """Lowercase, drop dots (so 'U.S.'->'us', 'A.B.'->'ab'), strip remaining
    punctuation to single spaces, collapse, trim."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace(".", "")).strip()


# ==========================================================================
# Policies / bills
# ==========================================================================

# Known named programs -> (policy_id, canonical display name). Keyed by _norm.
POLICY_ALIASES: dict[str, tuple[str, str]] = {
    "aca": ("us_aca", "Affordable Care Act (ACA)"),
    "obamacare": ("us_aca", "Affordable Care Act (ACA)"),
    "affordable care act": ("us_aca", "Affordable Care Act (ACA)"),
    "patient protection and affordable care act": ("us_aca", "Affordable Care Act (ACA)"),
    "snap": ("us_snap", "Supplemental Nutrition Assistance Program (SNAP)"),
    "food stamps": ("us_snap", "Supplemental Nutrition Assistance Program (SNAP)"),
    "supplemental nutrition assistance program": ("us_snap", "Supplemental Nutrition Assistance Program (SNAP)"),
    "supplemental nutrition assistance program snap": ("us_snap", "Supplemental Nutrition Assistance Program (SNAP)"),
    "medicaid": ("us_medicaid", "Medicaid"),
    "medicare": ("us_medicare", "Medicare"),
    "chip": ("us_chip", "Children's Health Insurance Program (CHIP)"),
    "children s health insurance program": ("us_chip", "Children's Health Insurance Program (CHIP)"),
    "head start": ("us_head_start", "Head Start"),
    "tanf": ("us_tanf", "Temporary Assistance for Needy Families (TANF)"),
    "temporary assistance for needy families": ("us_tanf", "Temporary Assistance for Needy Families (TANF)"),
    "section 8": ("us_section8", "Housing Choice Voucher Program (Section 8)"),
    "housing choice voucher": ("us_section8", "Housing Choice Voucher Program (Section 8)"),
    "title iv e": ("us_title_ive", "Title IV-E (Social Security Act)"),
    "fiscal responsibility act": ("us_fra_2023", "Fiscal Responsibility Act of 2023"),
    "fiscal responsibility act of 2023": ("us_fra_2023", "Fiscal Responsibility Act of 2023"),
}

# Bill number: chamber prefix (with optional dots) + number. Covers CA (SB/AB),
# NY (S/A), federal (HR/S), and resolution/joint forms.
_BILL_RE = re.compile(
    r"(?i)\b(S\.?B|A\.?B|H\.?B|H\.?R|S\.?R|S\.?C\.?R|A\.?C\.?R|S\.?J\.?R|H\.?J\.?R|SB|AB|HB|HR|SR|S|A|H)\.?\s*-?\s*(\d{1,5})\b"
)


def normalize_bill(name: str) -> tuple[str, str] | None:
    """Return (prefix, number) canonicalized, or None if not a bill reference."""
    m = _BILL_RE.search(name or "")
    if not m:
        return None
    prefix = m.group(1).upper().replace(".", "")
    return prefix, m.group(2)


def resolve_policy(surface: str, state: str | None) -> tuple[str, str, str]:
    """Resolve one policy surface -> (policy_id, canonical_name, match_method)."""
    n = _norm(surface)
    if n in POLICY_ALIASES:
        pid, cname = POLICY_ALIASES[n]
        return pid, cname, "alias"
    bill = normalize_bill(surface)
    if bill:
        prefix, num = bill
        st = (state or "").upper()
        qual = f"{st}-" if st in _TERRITORY else ""
        return f"bill_{qual}{prefix}-{num}".lower(), f"{prefix} {num}", "bill"
    return f"pol_{_hash12(n)}", surface.strip(), "surface"


# ==========================================================================
# Organizations
# ==========================================================================

# Alias seed for common agencies -> (org_id, canonical name). Keyed by _norm.
ORG_ALIASES: dict[str, tuple[str, str]] = {
    "acs": ("org_nyc_acs", "NYC Administration for Children's Services (ACS)"),
    "administration for children s services": ("org_nyc_acs", "NYC Administration for Children's Services (ACS)"),
    "nyc administration for children s services": ("org_nyc_acs", "NYC Administration for Children's Services (ACS)"),
    "dhcs": ("org_ca_dhcs", "California Department of Health Care Services (DHCS)"),
    "department of health care services": ("org_ca_dhcs", "California Department of Health Care Services (DHCS)"),
    "california department of health care services": ("org_ca_dhcs", "California Department of Health Care Services (DHCS)"),
    "cdss": ("org_ca_cdss", "California Department of Social Services (CDSS)"),
    "california department of social services": ("org_ca_cdss", "California Department of Social Services (CDSS)"),
    "hhs": ("org_us_hhs", "U.S. Department of Health and Human Services (HHS)"),
    "department of health and human services": ("org_us_hhs", "U.S. Department of Health and Human Services (HHS)"),
    "us department of health and human services": ("org_us_hhs", "U.S. Department of Health and Human Services (HHS)"),
    "hud": ("org_us_hud", "U.S. Department of Housing and Urban Development (HUD)"),
    "department of housing and urban development": ("org_us_hud", "U.S. Department of Housing and Urban Development (HUD)"),
    "fema": ("org_us_fema", "Federal Emergency Management Agency (FEMA)"),
    "federal emergency management agency": ("org_us_fema", "Federal Emergency Management Agency (FEMA)"),
    "nws": ("org_us_nws", "National Weather Service (NWS)"),
    "national weather service": ("org_us_nws", "National Weather Service (NWS)"),
    "cps": ("org_cps", "Child Protective Services (CPS)"),
    "child protective services": ("org_cps", "Child Protective Services (CPS)"),
}

_PAREN_ACRONYM_RE = re.compile(r"\(([A-Z][A-Za-z&.]{1,7})\)")


def strip_parenthetical(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", name or "").strip()


def extract_paren_acronym(name: str) -> str | None:
    """The acronym inside parentheses, e.g. '... Services (DHCS)' -> 'DHCS'."""
    m = _PAREN_ACRONYM_RE.search(name or "")
    if not m:
        return None
    acr = m.group(1)
    return acr if sum(c.isupper() for c in acr) >= 2 else None


def is_acronymic(name: str) -> bool:
    """True for a standalone acronym token like 'DHCS', 'HHS', 'FEMA'."""
    t = (name or "").strip().replace(".", "")
    return 2 <= len(t) <= 6 and t.isupper() and t.isalpha()


def resolve_org_surfaces(surfaces) -> dict[str, tuple[str, str, str]]:
    """Resolve a collection of org surfaces (may repeat) to canonical ids.

    Returns {surface: (org_id, canonical_name, match_method)}. Two passes:
    first assign each surface a key (alias > base-name hash), registering any
    parenthetical acronym -> key; then bind standalone-acronym surfaces to a
    registered key. Canonical name = alias name, else the most frequent
    non-acronym surface for the key.
    """
    counts = Counter(s.strip() for s in surfaces if s and s.strip())
    info: dict[str, dict] = {}
    acr_to_key: dict[str, str] = {}

    for surf, cnt in counts.items():
        base = strip_parenthetical(surf)
        alias = ORG_ALIASES.get(_norm(surf)) or ORG_ALIASES.get(_norm(base))
        if alias:
            key, method, alias_name = alias[0], "alias", alias[1]
        else:
            key, method, alias_name = f"org_{_hash12(_norm(base))}", "base", None
        info[surf] = {
            "key": key, "method": method, "alias_name": alias_name,
            "is_acr": is_acronymic(surf), "cnt": cnt,
        }
        acr = extract_paren_acronym(surf)
        if acr:
            acr_to_key.setdefault(_norm(acr), key)

    # pass 2: standalone acronym surfaces bind to a registered parenthetical key
    for surf, d in info.items():
        if d["method"] == "base" and d["is_acr"]:
            k = acr_to_key.get(_norm(surf))
            if k and k != d["key"]:
                d["key"], d["method"] = k, "acronym"

    # canonical display name per key
    key_name: dict[str, tuple[tuple, str]] = {}
    for surf, d in info.items():
        if d["alias_name"]:
            key_name[d["key"]] = ((9, 9, 9), d["alias_name"])
            continue
        score = (0 if d["is_acr"] else 1, d["cnt"], len(surf))
        cur = key_name.get(d["key"])
        if cur is None or score > cur[0]:
            key_name[d["key"]] = (score, surf.strip())

    return {surf: (d["key"], key_name[d["key"]][1], d["method"]) for surf, d in info.items()}


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
