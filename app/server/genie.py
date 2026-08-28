"""Genie 'Topic Deep-Dive' client + serialization.

Ports the BrickHearts Topic Deep-Dive notebook: given a Hot-Issue card's topic +
region (and the optional card context the card already shows), ask the certified
Genie space its findings query and serialize the returned rows into the fixed
payload the Deep Dive page renders. Genie does the analysis — there is no second
LLM. Auth reuses the app's WorkspaceClient (app SP when deployed, CLI profile
locally), so no extra token handling.
"""

from __future__ import annotations

import datetime
import re
import time

import requests

from . import config


def _strip_trailing_question(text: str) -> str:
    """Genie sometimes ends the narrative with a conversational follow-up question
    ("Would you prefer ...?"). Drop a trailing question sentence so the narrative
    ends on the recommended next step."""
    text = (text or "").strip()
    if not text.endswith("?"):
        return text
    # Cut at the last sentence terminator before the final question.
    boundaries = list(re.finditer(r"[.!?]\s+", text))
    if boundaries:
        return text[: boundaries[-1].end()].strip()
    return text  # single-sentence question — leave as-is

# The card-aware prompt the backend fills. Topic + region drive the certified
# query; the card context anchors Genie's narrative to the exact signals shown.
PROMPT_TEMPLATE = (
    'Return the canonical findings for the topic "{topic}"{region_clause}.\n'
    "Card context — anchor the analysis to this card: {signal_count} signals ({signal_mix}); "
    "next/latest date {latest}; key dates {key_dates}; sources {sources}.\n"
    "Then look ACROSS the {region_name} data for non-obvious next steps the card does not show: "
    "which named nonprofits or churches (not government bodies) are already connected or funded and "
    "could be recruited now; whether the need also clusters in other {region_name} places; which "
    "upcoming hearing is the single best entry point; what funding is already in play and who received "
    "it; and where families are in acute crisis right now. End with the one best next step."
)


def build_question(topic: str, region: str, card: dict) -> str:
    region_clause = "" if region in ("All", "") else f" in {region}"
    region_name = "national" if region in ("All", "") else region
    return PROMPT_TEMPLATE.format(
        topic=topic,
        region_clause=region_clause,
        region_name=region_name,
        signal_count=card.get("signal_count") or "several",
        signal_mix=card.get("signal_mix") or "mixed",
        latest=card.get("latest") or "n/a",
        key_dates=card.get("key_dates") or "n/a",
        sources=card.get("sources") or "n/a",
    )


def _auth() -> tuple[str, dict]:
    """(genie base url, request headers) using the app's WorkspaceClient auth."""
    w = config.get_workspace_client()
    host = w.config.host.rstrip("/")
    token = w.config.authenticate().get("Authorization", "").removeprefix("Bearer ").strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return f"{host}/api/2.0/genie/spaces/{config.GENIE_SPACE_ID}", headers


def ask_genie(question: str, timeout: int = 180) -> dict:
    """Start a Genie conversation, poll to completion, return text + tabular rows."""
    base, headers = _auth()
    r = requests.post(
        f"{base}/start-conversation", headers=headers, json={"content": question}, timeout=30
    )
    r.raise_for_status()
    j = r.json()
    cid, mid = j["conversation_id"], j["message_id"]

    deadline, msg = time.time() + timeout, {}
    while time.time() < deadline:
        msg = requests.get(
            f"{base}/conversations/{cid}/messages/{mid}", headers=headers, timeout=30
        ).json()
        if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(4)

    text, columns, rows = [], [], []
    for att in msg.get("attachments", []):
        if att.get("text", {}).get("content"):
            text.append(att["text"]["content"])
        if att.get("query"):
            aid = att["attachment_id"]
            qr = requests.get(
                f"{base}/conversations/{cid}/messages/{mid}/attachments/{aid}/query-result",
                headers=headers,
                timeout=60,
            ).json()
            sr = qr.get("statement_response", {})
            man, res = sr.get("manifest", {}), sr.get("result", {})
            if man and res:
                columns = [c["name"] for c in man["schema"]["columns"]]
                rows = res.get("data_array", []) or []
    return {
        "status": msg.get("status"),
        "text": "\n".join(text).strip(),
        "columns": columns,
        "rows": rows,
    }


def _ci(cols: list[str], name: str) -> int | None:
    low = [c.lower() for c in cols]
    return low.index(name) if name in low else None


def _render(ftype, subject, detail, metric, event_date, source) -> tuple[str, str]:
    """Human-readable finding + decision-oriented so_what per category."""
    src = f" [{source}]" if source else ""
    if ftype == "hot_place":
        loc = f"{subject} ({detail})" if detail else subject
        return (
            f"{loc} — {metric} signals for this topic.",
            "Where the need concentrates; scope a territory push or check for a local crisis cluster here.",
        )
    if ftype == "named_responder":
        org = f"{subject} ({detail})" if detail else subject
        return (
            f"{org} is a community responder connected to this topic.",
            "Recruitable now — a church, nonprofit, business or school already tied to these signals.",
        )
    if ftype == "related_issue":
        return (
            f"Also affects {subject} — {metric} shared signals.",
            f"Families here likely need {subject} help too; recruit responders who can serve both.",
        )
    if ftype == "upcoming_event":
        when = f" on {event_date}" if event_date else ""
        return (
            f"Upcoming: {subject} in {detail}{when} (priority {metric}).{src}",
            "A dated entry point — line up responders to show before this hearing/decision.",
        )
    if ftype == "funding_hook":
        when = f" ({event_date})" if event_date else ""
        return (
            f"Funding in play{when}: {subject}{src}",
            "Money is already committed — align outreach with the funded programs and named recipients.",
        )
    if ftype == "crisis_signal":
        when = f" ({event_date})" if event_date else ""
        return (
            f"Acute need{when}: {subject}{src}",
            "Families in crisis now — a concrete, human case to mobilize responders around.",
        )
    return (f"{subject} ({metric})", "")


def _serialize(ans: dict) -> dict:
    """Turn Genie's rows into the fixed findings payload (analysis envelope)."""
    findings, responders, events, funding, crises = [], [], [], [], []
    cols = ans["columns"]
    if cols and ans["rows"]:
        it, isub, idet = _ci(cols, "finding_type"), _ci(cols, "subject"), _ci(cols, "detail")
        imet, idate, isrc = _ci(cols, "metric"), _ci(cols, "event_date"), _ci(cols, "source")
        iurl, iq = _ci(cols, "source_url"), _ci(cols, "quote")
        for row in ans["rows"]:
            ftype = (row[it] if it is not None else "") or ""
            subject = row[isub] if isub is not None else ""
            detail = (row[idet] if idet is not None else "") or ""
            metric_raw = row[imet] if imet is not None else None
            try:
                metric = int(float(metric_raw)) if metric_raw not in (None, "") else None
            except (TypeError, ValueError):
                metric = metric_raw
            event_date = (row[idate] if idate is not None else "") or ""
            source = (row[isrc] if isrc is not None else "") or ""
            source_url = (row[iurl] if iurl is not None else "") or ""
            quote = (row[iq] if iq is not None else "") or ""
            finding_text, so_what = _render(ftype, subject, detail, metric, event_date, source)
            obj = {
                "category": ftype,
                "subject": subject,
                "detail": detail or None,
                "metric": metric,
                "event_date": event_date or None,
                "source": source or None,
                "source_url": source_url or None,
                "quote": quote or None,
                "finding": finding_text,
                "so_what": so_what,
            }
            findings.append(obj)
            if ftype == "named_responder":
                responders.append(f"{subject} ({detail})" if detail else subject)
            elif ftype == "upcoming_event":
                events.append(obj)
            elif ftype == "funding_hook":
                funding.append(obj)
            elif ftype == "crisis_signal":
                crises.append(obj)

    places = [f for f in findings if f["category"] == "hot_place"]

    if events:
        e = sorted(events, key=lambda x: x["event_date"] or "9999")[0]
        recommended_play = (
            f'Recruit responders in {e["detail"]} ahead of "{e["subject"]}"'
            f'{(" on " + e["event_date"]) if e["event_date"] else ""} — the nearest dated window.'
        )
    elif funding:
        recommended_play = "Engage the named recipients of the funding already committed (see funding hooks)."
    elif places:
        recommended_play = (
            f"Start in {places[0]['subject']} — the highest-signal location — "
            "and recruit the connected community responders."
        )
    else:
        recommended_play = "Insufficient data in scope."

    clusters = [p["subject"] for p in places]
    if len(clusters) >= 2:
        headline = (
            f"{clusters[0]} leads, but need also shows in {', '.join(clusters[1:3])} — "
            f"{len(responders)} community responders and {len(events)} dated windows are in reach."
        )
    elif clusters:
        headline = f"{clusters[0]} is the focal point; {len(responders)} community responders connected."
    else:
        headline = ans["text"].split("\n")[0][:200] if ans["text"] else "Insufficient data in scope."

    watch_outs = (
        "Crisis signals are grassroots reports (verify individually); confirm hearing dates and "
        "funding figures against the cited sources before external outreach."
        if crises
        else "Verify dates, figures, and org names against the cited sources before external outreach."
    )

    return {
        "headline": headline,
        "findings": findings,
        "who_to_recruit": responders,
        "recommended_play": recommended_play,
        "watch_outs": watch_outs,
    }


def deep_dive(topic: str, region: str, card: dict, timeout: int = 180) -> dict:
    """Full flow: fill prompt → ask Genie → serialize into the render payload."""
    question = build_question(topic, region, card)
    ans = ask_genie(question, timeout=timeout)
    analysis = _serialize(ans)
    return {
        "topic": topic,
        "region": region,
        "card_context": card,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "genie_space_id": config.GENIE_SPACE_ID,
        "genie_status": ans["status"],
        "row_count": len(ans["rows"]),
        **analysis,
        "narrative": _strip_trailing_question(ans["text"]),
    }
