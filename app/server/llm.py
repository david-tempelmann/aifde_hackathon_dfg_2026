"""Grounded outreach-draft generation via a Databricks Foundation Model.

An outreach worker picks an opportunity and one or more *variants* (audience +
channel + tone); the model drafts each, grounded strictly on the opportunity's
own fields and citations plus a small set of approved GO Project / CarePortal
facts. Drafts are AI-generated and labelled for human review (design §3 Action
studio). Variants are generated in parallel to keep latency down.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

from . import config

# Approved facts the draft may reference (from the GO Project brief). Keeping
# these server-side prevents the model from inventing organizational claims.
_GO_FACTS = """\
- The Global Orphan (GO) Project, founded in 2004, serves 110,000+ children annually across 11 countries.
- CarePortal is GO Project's technology platform that connects local churches and community "responders" to real-time needs of children and families identified by social workers/caseworkers.
- CarePortal has connected tens of thousands of community responders to meet the needs of children in crisis.
- GO Project holds a 4/4-star Charity Navigator rating and runs on a 100%-donor-covered overhead model.
- CarePortal's voice is warm, human, and action-oriented ("compassionately savvy")."""

_SYSTEM = f"""\
You are an outreach assistant for a GO Project State Director. You draft short, credible \
outreach messages that recruit prospective CarePortal partners by connecting a specific, timely \
local development to how CarePortal helps children and families.

Approved facts you may use:
{_GO_FACTS}

Strict rules:
- Ground the message ONLY in the SIGNAL DETAILS and CITED EVIDENCE provided, plus the approved facts above.
- Do NOT invent statistics, names, dates, or quotes. Use only numbers/claims that appear in the provided material.
- Reference the specific local issue and development, and make one clear, low-pressure ask.
- Plain, human, and warm. No emojis, no hype, no fabricated signature — end with a simple "[Your name], GO Project" placeholder.
- Follow the VARIANT INSTRUCTIONS for audience, channel, tone, length, and format exactly.
- Output only the message text (nothing else)."""


# Variant registry — organized by CHANNEL / FORMAT (recipient-agnostic). The
# recipient/audience is a separate input the worker fills in. Start with a few;
# add or rename here.
VARIANTS: dict[str, dict] = {
    "email": {
        "label": "Email",
        "channel": "email",
        "instructions": "Format: an email with a subject line on the first line. Tone: warm, credible, "
        "community-minded. Length: 120-170 words.",
    },
    "short_message": {
        "label": "Short message",
        "channel": "message",
        "instructions": "Format: a short direct message, no subject line. Tone: concise, peer-to-peer, "
        "mission-aligned. Length: 60-90 words.",
    },
    "sms": {
        "label": "SMS",
        "channel": "sms",
        "instructions": "Format: a single SMS. Tone: friendly, direct. Length: under 320 characters. "
        "No subject line; a brief '- GO Project' sign-off is fine.",
    },
    "community_callout": {
        "label": "Community call-to-action",
        "channel": "post",
        "instructions": "Format: a short, punchy public call-to-action (social post or flyer blurb) in second "
        "person, 1-3 sentences, no sign-off. Tone: civic and motivating. Name the specific local development, then "
        "invite the reader to get involved via the GO Project's CarePortal. Shape it like: 'Your city council is "
        "debating <issue>. To make an impact in your community, check out the GO Project's CarePortal.'",
    },
    # --- Ready to enable next (build-out) ---
    "formal_letter": {
        "label": "Formal letter",
        "channel": "email",
        "instructions": "Format: a formal letter/email with a subject line. Tone: professional, respectful, "
        "precise. Length: 130-180 words.",
    },
    "phone_script": {
        "label": "Phone-call script",
        "channel": "call",
        "instructions": "Format: a short spoken call script with a one-line opener, 2-3 talking points, and a "
        "closing ask. Tone: warm, conversational. Length: 120-160 words.",
    },
}

DEFAULT_VARIANTS = ["email", "short_message", "community_callout"]


def _fmt_citations(citations: list[dict]) -> str:
    lines = []
    for c in citations:
        quote = (c.get("quote") or "").strip()
        src = c.get("source_name") or "source"
        if quote:
            lines.append(f'- "{quote}" — {src}')
    return "\n".join(lines) or "(no citations available)"


def _base_context(opp: dict, citations: list[dict], partner_name: str | None) -> str:
    pops = opp.get("affected_populations") or []
    pops_str = ", ".join(pops) if isinstance(pops, list) else str(pops)
    place = opp.get("place_name") or opp.get("state") or "the region"
    recipient = partner_name.strip() if partner_name and partner_name.strip() else "a prospective CarePortal partner"
    return f"""\
Recipient: {recipient} in {place}.

SIGNAL DETAILS
- Headline: {opp.get('summary') or ''}
- Issue: {opp.get('issue_label') or ''}
- Location: {place} ({opp.get('state') or ''})
- Relevance: {opp.get('relevance_direction') or ''}
- Why it matters to GO/CarePortal: {opp.get('why_go') or ''}
- Suggested angle: {opp.get('recommended_action') or ''}
- Affected populations: {pops_str or 'not specified'}

CITED EVIDENCE (the only external facts you may cite)
{_fmt_citations(citations)}"""


def _draft_one(context: str, variant_key: str) -> dict:
    spec = VARIANTS[variant_key]
    user = f"{context}\n\nVARIANT INSTRUCTIONS\n{spec['instructions']}\n\nWrite the message now."
    client = config.get_workspace_client()
    resp = client.serving_endpoints.query(
        name=config.SERVING_ENDPOINT,
        messages=[
            ChatMessage(role=ChatMessageRole.SYSTEM, content=_SYSTEM),
            ChatMessage(role=ChatMessageRole.USER, content=user),
        ],
        max_tokens=700,
        temperature=0.5,
    )
    return {
        "key": variant_key,
        "label": spec["label"],
        "channel": spec["channel"],
        "draft": (resp.choices[0].message.content or "").strip(),
    }


_JUDGE_SYSTEM = """\
You are a bilingual localization reviewer for community outreach messages. Given an English \
original and its machine translation into a target language, rate the translation for a \
community-outreach audience on three things: accuracy (meaning preserved), fluency (reads \
naturally to a native speaker), and cultural appropriateness (respectful, natural terminology \
for that community). Return ONLY a JSON object, no prose:
{"score": <integer 0-100>, "assessment": "<one or two sentences: what's good, and any wording or terminology to adjust>"}"""


def score_translation(original: str, translated: str, target_lang: str) -> dict:
    """LLM-judge the translation quality; returns {score:int|None, assessment:str}."""
    user = (
        f"Target language code: {target_lang}\n\n"
        f"ENGLISH ORIGINAL:\n{original}\n\nTRANSLATION:\n{translated}"
    )
    client = config.get_workspace_client()
    resp = client.serving_endpoints.query(
        name=config.SERVING_ENDPOINT,
        messages=[
            ChatMessage(role=ChatMessageRole.SYSTEM, content=_JUDGE_SYSTEM),
            ChatMessage(role=ChatMessageRole.USER, content=user),
        ],
        max_tokens=300,
        temperature=0.0,
    )
    text = (resp.choices[0].message.content or "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            obj = json.loads(match.group(0))
            score = obj.get("score")
            return {
                "score": int(score) if isinstance(score, (int, float)) else None,
                "assessment": str(obj.get("assessment", "")).strip(),
            }
        except (ValueError, TypeError):
            pass
    return {"score": None, "assessment": text[:300]}


def draft_variants(
    opp: dict,
    citations: list[dict],
    *,
    variant_keys: list[str] | None = None,
    partner_name: str | None = None,
) -> list[dict]:
    """Generate the requested variants in parallel. Returns a list per variant."""
    keys = [k for k in (variant_keys or DEFAULT_VARIANTS) if k in VARIANTS] or DEFAULT_VARIANTS
    context = _base_context(opp, citations, partner_name)
    with ThreadPoolExecutor(max_workers=min(len(keys), 6)) as pool:
        results = list(pool.map(lambda k: _draft_one(context, k), keys))
    # Preserve requested order.
    order = {k: i for i, k in enumerate(keys)}
    results.sort(key=lambda r: order.get(r["key"], 99))
    return results
