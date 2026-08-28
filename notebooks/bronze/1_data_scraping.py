# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # BrickHearts — News & Signal API Probe
# MAGIC
# MAGIC **Global Orphan / CarePortal hackathon.** A first probe to confirm we can retrieve
# MAGIC **latest news** and **need signals** from free, keyless, public sources for our three
# MAGIC regions: **New York, California, Virginia**.
# MAGIC
# MAGIC This notebook is **display-only** — nothing is written to Unity Catalog yet. It proves
# MAGIC live retrieval works and shows a normalized preview we can later land as a bronze table.
# MAGIC
# MAGIC | Section | Source | Auth |
# MAGIC |---|---|---|
# MAGIC | 1 / 1a | RSS feeds from nonprofit newsrooms (CalMatters, KQED, The City, Gothamist, Cardinal News, ProPublica, The 19th) + full article text | none |
# MAGIC | 1b | Google News RSS by region + topic (fallback / booster) | none |
# MAGIC | 1c | Datacenter-IP-blocked feeds (Virginia Mercury, NPR, Stateline) via **Bright Data** Web Unlocker + full article text | secret |
# MAGIC | 1d | **Bluesky** keyword search by region+topic (grassroots social signal); post text = content | secret (app pw) |
# MAGIC | 1e | **Government** — Legistar laws + **agenda PDFs (full text extracted)**, Federal Register, CA Governor (`source_type=government`) | none |
# MAGIC | 2. Weather | api.weather.gov active alerts | none |
# MAGIC | 3. Disaster | OpenFEMA disaster declarations | none |
# MAGIC | 4. Combined | Normalized preview across all sources (content included) | — |
# MAGIC
# MAGIC > Runs on Python (stdlib + pandas + trafilatura). Attach to serverless or any cluster.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0a. Install deps
# MAGIC `trafilatura` extracts clean main-body article text; `pypdf` extracts text from agenda
# MAGIC PDFs — both feed downstream NER/extraction. `%pip` restarts Python, so this must run first.

# COMMAND ----------

# MAGIC %pip install --quiet trafilatura pypdf
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Config & helpers

# COMMAND ----------

import urllib.request
import urllib.parse
import urllib.error
import json
import ssl
import re
import gzip
import io
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import pandas as pd

pd.set_option("display.max_colwidth", 90)

USER_AGENT = "BrickHearts-Hackathon/0.1 (GlobalOrphanProject; contact julie.nguyen@databricks.com)"
# Some CDNs (e.g. Cloudflare on gov.ca.gov) 403 the verbose UA above; a plain browser UA passes.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
_SSL_CTX = ssl.create_default_context()


def fetch(url, timeout=20, accept=None, ua=None):
    """GET a URL. Returns (status, bytes) or raises. Pass `ua` to override the User-Agent."""
    headers = {"User-Agent": ua or USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return resp.status, resp.read()


def parse_when(s):
    """Best-effort parse of RSS/Atom date strings to a UTC datetime, else None."""
    if not s:
        return None
    s = s.strip()
    # RFC 822 (RSS <pubDate>)
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # ISO 8601 (Atom <updated>/<published>)
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Latest news — nonprofit newsroom RSS feeds
# MAGIC
# MAGIC Curated free/CC-licensed civic newsrooms. Each feed reports **OK / FAIL** so we can see
# MAGIC exactly which sources retrieve. `region` and bias are tagged per our source catalog.

# COMMAND ----------

# region | source name | rss url | bias (AllSides/MBFC approx — verify live)
# NOTE: all 7 below were verified to retrieve live (2026-08-26). A few otherwise-good
# nonprofit feeds block datacenter IPs with HTTP 403 (Virginia Mercury, NPR, Stateline) —
# for those, use the Google News RSS fallback in section 1b, or route via Bright Data.
FEEDS = [
    ("CA",  "CalMatters",  "https://calmatters.org/feed/",                       "Center"),
    ("CA",  "KQED",        "https://ww2.kqed.org/news/feed/",                    "Lean Left"),
    ("NY",  "The City",    "https://www.thecity.nyc/feed/",                      "Center/Lean Left"),
    ("NY",  "Gothamist",   "https://gothamist.com/feed",                         "Lean Left"),
    ("VA",  "Cardinal News","https://cardinalnews.org/feed/",                    "Center"),
    ("US",  "ProPublica",  "https://www.propublica.org/feeds/propublica/main",   "Lean Left"),
    ("US",  "The 19th",    "https://19thnews.org/feed/",                         "Lean Left"),
]

# Social-need keywords used only to FLAG relevant items (nothing is filtered out here).
KEYWORDS = [
    "homeless", "housing", "eviction", "foster", "child welfare", "poverty",
    "shelter", "food bank", "food insecurity", "family", "youth", "disaster",
    "displaced", "affordable", "rent", "hunger",
]


def strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_feed(xml_bytes, max_items=8):
    """Parse RSS 2.0 or Atom. Returns dicts with title, link, when(+dt), summary, content_html.
    `content_html` holds <content:encoded> (RSS) or <content> (Atom) when the feed embeds the
    full article; `summary` holds <description>/<summary> (usually just a teaser)."""
    root = ET.fromstring(xml_bytes)
    items = []
    nodes = [e for e in root.iter() if strip_ns(e.tag) in ("item", "entry")]
    for node in nodes[:max_items]:
        title = link = when = summary = content_html = None
        for child in node:
            t = strip_ns(child.tag)
            if t == "title" and title is None:
                title = (child.text or "").strip()
            elif t == "link":
                if child.text and child.text.strip():
                    link = child.text.strip()
                elif child.get("href"):
                    if child.get("rel") in (None, "alternate") or link is None:
                        link = child.get("href")
            elif t in ("pubDate", "published", "updated") and when is None:
                when = (child.text or "").strip()
            elif t in ("description", "summary") and summary is None:
                summary = child.text or ""
            elif t in ("encoded", "content"):  # content:encoded (RSS) / content (Atom)
                content_html = child.text or (content_html or "")
        items.append({"title": title, "link": link, "when": when,
                      "when_dt": parse_when(when),
                      "summary": summary or "", "content_html": content_html or ""})
    return items


class _TextExtractor(HTMLParser):
    """Stdlib fallback: pull readable text from <p> tags, skipping script/style."""
    def __init__(self):
        super().__init__()
        self._skip = 0
        self._in_p = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "p":
            self._in_p = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "p":
            self._in_p = False
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and self._in_p:
            self.parts.append(data)


def html_to_text(html):
    if not html:
        return ""
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:
        return ""
    text = "".join(p.parts)
    return re.sub(r"\n{2,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def extract_article(url, feed_content_html="", min_chars=600, timeout=25, fetcher=None):
    """Return (text, method). Prefer feed-embedded full content; else fetch page and use
    trafilatura; else fall back to a <p>-tag text extractor. `fetcher` lets callers route the
    page fetch through Bright Data (bright_fetch) while keeping identical extraction logic."""
    fetcher = fetcher or fetch
    # 1) Feed already embedded the full body (common for WordPress content:encoded)
    embedded = html_to_text(feed_content_html)
    if len(embedded) >= min_chars:
        return embedded, "feed:content:encoded"
    # 2) Fetch the article page and extract main content
    try:
        _, body = fetcher(url, timeout=timeout, accept="text/html,application/xhtml+xml,*/*")
        html = body.decode("utf-8", errors="replace")
    except Exception as e:
        return (embedded, "feed-summary-only") if embedded else ("", f"fetch-failed:{type(e).__name__}")
    try:
        import trafilatura
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False,
                                        favor_precision=True)
        if extracted and len(extracted) >= 200:
            return extracted.strip(), "trafilatura"
    except Exception:
        pass
    # 3) Stdlib fallback
    fallback = html_to_text(html)
    if len(fallback) >= 200:
        return fallback, "html-p-tags"
    return (embedded, "feed-summary-only") if embedded else (fallback, "html-p-tags-thin")


def extract_pdf_text(pdf_bytes, max_pages=40):
    """Extract text from a PDF byte string via pypdf. Returns '' on failure or image-only
    (scanned) PDFs that carry no extractable text layer."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join((pg.extract_text() or "") for pg in reader.pages[:max_pages])
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception:
        return ""


rows = []
status_rows = []
for region, name, url, bias in FEEDS:
    try:
        code, body = fetch(url, accept="application/rss+xml, application/xml, text/xml, */*")
        items = parse_feed(body)
        status_rows.append({"source": name, "region": region, "status": f"OK ({code})",
                            "items": len(items), "bias": bias, "url": url})
        for it in items:
            title = it["title"] or ""
            flagged = any(k in title.lower() for k in KEYWORDS)
            rows.append({
                "source": name,
                "region": region,
                "bias": bias,
                "title": title,
                "date": it["when_dt"].strftime("%Y-%m-%d %H:%M") if it["when_dt"] else (it["when"] or ""),
                "when_dt": it["when_dt"],
                "relevant": "★" if flagged else "",
                "url": it["link"] or "",
                "summary": html_to_text(it.get("summary", ""))[:400],
                "content_html": it.get("content_html", ""),
                "source_type": "news",
            })
    except Exception as e:
        status_rows.append({"source": name, "region": region, "status": f"FAIL: {type(e).__name__}: {e}",
                            "items": 0, "bias": bias, "url": url})

status_df = pd.DataFrame(status_rows)[["source", "region", "status", "items", "bias", "url"]]
print("Feed retrieval status:")
display(status_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Latest headlines (all feeds, newest first)
# MAGIC `★` = matches a social-need keyword (homelessness, housing, foster, eviction, …).

# COMMAND ----------

news_df = pd.DataFrame(rows)
if not news_df.empty:
    news_df = news_df.sort_values("when_dt", ascending=False, na_position="last")
    display(news_df[["date", "source", "region", "relevant", "title", "url"]])
else:
    print("No news items retrieved — check the status table above.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Just the socially-relevant headlines
# MAGIC The subset an outreach worker would actually care about.

# COMMAND ----------

if not news_df.empty:
    rel = news_df[news_df["relevant"] == "★"]
    print(f"{len(rel)} of {len(news_df)} retrieved headlines matched social-need keywords.")
    display(rel[["date", "source", "region", "title", "url"]])
else:
    print("No news items to filter.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1a. Full article text (for downstream NER / extraction)
# MAGIC For each item we fetch the article body and extract **clean main-body text** —
# MAGIC first from the feed's embedded `content:encoded` if present, else via **trafilatura**
# MAGIC (boilerplate removed), else a stdlib `<p>`-tag fallback. `extract_method` shows which
# MAGIC path won so you can judge quality per source.
# MAGIC
# MAGIC Runtime note: each article is one HTTP fetch, so we cap the count and prioritise the
# MAGIC socially-relevant (★) items. Raise `MAX_ARTICLES` / drop `RELEVANT_ONLY` to widen.

# COMMAND ----------

MAX_ARTICLES = 25          # cap total fetches to keep the probe fast
RELEVANT_ONLY = False      # True = only enrich ★ items

if not news_df.empty:
    target = news_df[news_df["relevant"] == "★"] if RELEVANT_ONLY else news_df
    # relevant first, then newest, then cap
    target = target.sort_values(["relevant", "when_dt"], ascending=[False, False],
                                na_position="last").head(MAX_ARTICLES)

    contents, methods, char_counts = {}, {}, {}
    for idx, r in target.iterrows():
        text, method = extract_article(r["url"], r.get("content_html", ""))
        contents[idx] = text
        methods[idx] = method
        char_counts[idx] = len(text)
        print(f"[{char_counts[idx]:6d} chars | {method:22s}] {r['source']:12s} {r['title'][:60]}")

    news_df["content"] = news_df.index.map(lambda i: contents.get(i, ""))
    news_df["extract_method"] = news_df.index.map(lambda i: methods.get(i, "skipped"))
    news_df["content_chars"] = news_df.index.map(lambda i: char_counts.get(i, 0))

    enriched = news_df[news_df["content_chars"] > 0].copy()
    print(f"\nExtracted body text for {len(enriched)} articles.")
    # extraction-method breakdown = quality signal per approach
    display(enriched.groupby("extract_method").size().reset_index(name="articles"))
else:
    print("No news items to enrich.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Article text preview
# MAGIC Title + first ~500 chars of the extracted body — sanity-check before NER.

# COMMAND ----------

if not news_df.empty and news_df["content_chars"].max() > 0:
    prev = news_df[news_df["content_chars"] > 0].sort_values("content_chars", ascending=False)
    prev = prev.assign(excerpt=prev["content"].str.slice(0, 500).str.replace(r"\s+", " ", regex=True))
    display(prev[["source", "region", "title", "content_chars", "extract_method", "excerpt"]])
else:
    print("No article bodies were extracted — check egress / the status table above.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1b. Fallback / booster — Google News RSS by region + topic (keyless)
# MAGIC Aggregated (mixed sources/bias — tag as such), but very reliable and guarantees fresh,
# MAGIC on-topic coverage for each state — including regions our curated feeds miss (e.g. VA).
# MAGIC Use to backfill sources that block datacenter IPs.

# COMMAND ----------

GNEWS_QUERIES = [
    ("NY", "homelessness OR foster care OR eviction New York"),
    ("CA", "homelessness OR foster care OR eviction California"),
    ("VA", "homelessness OR foster care OR eviction Virginia"),
]

gnews_rows = []
for region, query in GNEWS_QUERIES:
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en")
    try:
        code, body = fetch(url, accept="application/rss+xml, application/xml, */*")
        items = parse_feed(body, max_items=12)
        for it in items:
            gnews_rows.append({
                "source": "Google News (aggregated)",
                "region": region,
                "bias": "mixed",
                "title": it["title"] or "",
                "date": it["when_dt"].strftime("%Y-%m-%d %H:%M") if it["when_dt"] else (it["when"] or ""),
                "when_dt": it["when_dt"],
                "url": it["link"] or "",
                "source_type": "news-aggregated",
            })
        print(f"{region}: {len(items)} items for query '{query}'")
    except Exception as e:
        print(f"{region}: FAIL {type(e).__name__}: {e}")

gnews_df = pd.DataFrame(gnews_rows)
if not gnews_df.empty:
    gnews_df = gnews_df.sort_values("when_dt", ascending=False, na_position="last")
    display(gnews_df[["date", "region", "title", "url"]])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1c. Sources via Bright Data (free but datacenter-IP-blocked)
# MAGIC Some high-quality nonprofit feeds return **HTTP 403** to datacenter IPs (Databricks
# MAGIC egress included). We route both the **feed** and each **article** through the Bright Data
# MAGIC Web Unlocker API, then run the **same `parse_feed` + `extract_article`** pipeline — so
# MAGIC these rows come out with identical columns and full `content`, just fetched differently.
# MAGIC
# MAGIC The API token is read from the shared secret scope (`brickhearts` / `brightdata_api_key`);
# MAGIC set `BRIGHTDATA_ZONE` to match your Web Unlocker zone.

# COMMAND ----------

BRIGHTDATA_ZONE = "web_unlocker1"          # <-- your Bright Data Web Unlocker zone name
BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"

try:
    BRIGHTDATA_TOKEN = dbutils.secrets.get(scope="brickhearts", key="brightdata_api_key")
    print("Bright Data token loaded from secret scope 'brickhearts'.")
except Exception as e:
    BRIGHTDATA_TOKEN = None
    print(f"WARNING: could not read secret brickhearts/brightdata_api_key: {e}")


def bright_fetch(url, timeout=90, accept=None):
    """Fetch any URL through the Bright Data Web Unlocker API. Same (status, bytes) contract
    as fetch(), so it's a drop-in fetcher for parse_feed / extract_article.
    Raises with the API's own error text if the body comes back empty."""
    if not BRIGHTDATA_TOKEN:
        raise RuntimeError("BRIGHTDATA_TOKEN not set — check the secret scope.")
    payload = json.dumps({"zone": BRIGHTDATA_ZONE, "url": url,
                          "format": "raw", "method": "GET"}).encode()
    req = urllib.request.Request(
        BRIGHTDATA_ENDPOINT, data=payload,
        headers={"Authorization": f"Bearer {BRIGHTDATA_TOKEN}",
                 "Content-Type": "application/json",
                 "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            body = resp.read()
            if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
            status = resp.status
    except urllib.error.HTTPError as he:
        # Bright Data returns the reason in the error body — surface it
        detail = he.read()[:300].decode("utf-8", "replace")
        raise RuntimeError(f"Bright Data HTTP {he.code}: {detail}") from None
    if not body or not body.strip():
        # format:raw returns an empty body on denial — re-query in json mode to surface
        # Bright Data's own error (suspended account, bad zone, blocked target, etc.)
        try:
            j_payload = json.dumps({"zone": BRIGHTDATA_ZONE, "url": url,
                                    "format": "json", "method": "GET"}).encode()
            j_req = urllib.request.Request(
                BRIGHTDATA_ENDPOINT, data=j_payload,
                headers={"Authorization": f"Bearer {BRIGHTDATA_TOKEN}",
                         "Content-Type": "application/json", "User-Agent": USER_AGENT})
            with urllib.request.urlopen(j_req, timeout=timeout, context=_SSL_CTX) as jr:
                info = json.loads(jr.read().decode("utf-8", "replace"))
            errmsg = (info.get("headers", {}) or {}).get("x-brd-err-msg") or info.get("body") or info
            raise RuntimeError(f"Bright Data denied {url}: {errmsg}")
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError(f"Bright Data returned an EMPTY body (status {status}) for {url} — "
                               f"check the zone name and that the account/billing is active.")
    return status, body

# COMMAND ----------

# MAGIC %md
# MAGIC ### Bright Data self-test
# MAGIC Hits Bright Data's own test URL first, so we isolate token/zone problems from feed
# MAGIC problems. Expect a short "welcome" text and a 200.

# COMMAND ----------

if BRIGHTDATA_TOKEN:
    _test = "https://geo.brdtest.com/welcome.txt?product=unlocker&method=api"
    try:
        _c, _b = bright_fetch(_test)
        print(f"OK  status={_c}  bytes={len(_b)}")
        print("Head:", _b[:200].decode("utf-8", "replace").replace("\n", " "))
    except Exception as e:
        print(f"SELF-TEST FAILED: {type(e).__name__}: {e}")
        print("Fix this (usually BRIGHTDATA_ZONE) before the feeds below will work.")
else:
    print("No token — skipping self-test.")

# COMMAND ----------

# region | source | rss url | bias — free content, but block datacenter IPs directly
BRIGHT_FEEDS = [
    ("VA", "Virginia Mercury", "https://virginiamercury.com/feed/",  "Lean Left"),
    ("US", "NPR News",         "https://feeds.npr.org/1001/rss.xml", "Center/Lean Left"),
    ("US", "Stateline",        "https://stateline.org/feed/",        "Lean Left"),
]
BRIGHT_MAX_ARTICLES = 15   # cap article fetches (each is a Bright Data request = cost)

bright_rows, bright_status = [], []
if BRIGHTDATA_TOKEN:
    for region, name, url, bias in BRIGHT_FEEDS:
        body = b""
        try:
            code, body = bright_fetch(url, accept="application/rss+xml, application/xml, */*")
            items = parse_feed(body)
            bright_status.append({"source": name, "region": region, "status": f"OK ({code})",
                                  "items": len(items), "bias": bias, "url": url})
            for it in items:
                title = it["title"] or ""
                flagged = any(k in title.lower() for k in KEYWORDS)
                bright_rows.append({
                    "source": name, "region": region, "bias": bias, "title": title,
                    "date": it["when_dt"].strftime("%Y-%m-%d %H:%M") if it["when_dt"] else (it["when"] or ""),
                    "when_dt": it["when_dt"],
                    "relevant": "★" if flagged else "",
                    "url": it["link"] or "",
                    "summary": html_to_text(it.get("summary", ""))[:400],
                    "content_html": it.get("content_html", ""),
                    "source_type": "news",
                })
        except Exception as e:
            head = ""
            try:
                head = body[:160].decode("utf-8", "replace").replace("\n", " ")
            except Exception:
                pass
            bright_status.append({"source": name, "region": region,
                                  "status": f"FAIL: {type(e).__name__}: {e}",
                                  "items": 0, "bias": bias, "url": url})
            if head:
                print(f"  {name} raw response head: {head!r}")

    print("Bright Data feed status:")
    display(pd.DataFrame(bright_status)[["source", "region", "status", "items", "bias", "url"]])
else:
    print("Skipping Bright Data section — no token.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Enrich Bright Data articles with full text (via the same extractor)
# MAGIC Article pages fetched through `bright_fetch`, then `extract_article` → clean body text.

# COMMAND ----------

bright_df = pd.DataFrame(bright_rows)
if not bright_df.empty:
    # relevant first, newest next, then cap the number of (billable) article fetches
    order = bright_df.sort_values(["relevant", "when_dt"], ascending=[False, False],
                                  na_position="last").head(BRIGHT_MAX_ARTICLES)
    b_content, b_method, b_chars = {}, {}, {}
    for idx, r in order.iterrows():
        text, method = extract_article(r["url"], r.get("content_html", ""), fetcher=bright_fetch)
        b_content[idx], b_method[idx], b_chars[idx] = text, method, len(text)
        print(f"[{len(text):6d} chars | {method:22s}] {r['source']:16s} {r['title'][:55]}")

    bright_df["content"] = bright_df.index.map(lambda i: b_content.get(i, ""))
    bright_df["extract_method"] = bright_df.index.map(lambda i: b_method.get(i, "skipped"))
    bright_df["content_chars"] = bright_df.index.map(lambda i: b_chars.get(i, 0))
    bright_df = bright_df.sort_values("when_dt", ascending=False, na_position="last")

    got = bright_df[bright_df["content_chars"] > 0]
    print(f"\nBright Data: extracted body text for {len(got)} articles.")
    prev = got.assign(excerpt=got["content"].str.slice(0, 400).str.replace(r"\s+", " ", regex=True))
    display(prev[["date", "source", "region", "relevant", "title", "content_chars", "extract_method", "excerpt"]])
else:
    print("No Bright Data rows (no token, or all feeds failed).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1d. Social signal — Bluesky keyword search (free app password)
# MAGIC Grassroots / real-time community posts. Bluesky keyword search needs auth, so we log in
# MAGIC with a **free app password** (no credit card) read from the shared secret scope
# MAGIC (`brickhearts` / `bluesky_handle` + `bluesky_app_password`), then search per region+topic.
# MAGIC
# MAGIC The post text **is** the content, so these rows come out with the same columns and a
# MAGIC populated `content` field. Social is noisy → tagged `source_type=social`, `bias=mixed`;
# MAGIC weight it low in any confidence score.

# COMMAND ----------

BLUESKY_PDS = "https://bsky.social"

try:
    BSKY_HANDLE = dbutils.secrets.get(scope="brickhearts", key="bluesky_handle")
    BSKY_APP_PW = dbutils.secrets.get(scope="brickhearts", key="bluesky_app_password")
except Exception as e:
    BSKY_HANDLE = BSKY_APP_PW = None
    print(f"WARNING: could not read Bluesky secrets: {e}")


def bsky_login(identifier, password, timeout=30):
    """Create a Bluesky session → returns accessJwt."""
    payload = json.dumps({"identifier": identifier, "password": password}).encode()
    req = urllib.request.Request(
        BLUESKY_PDS + "/xrpc/com.atproto.server.createSession", data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read())["accessJwt"]


def bsky_search(jwt, q, limit=25, timeout=30):
    """app.bsky.feed.searchPosts via the PDS (proxies to the AppView)."""
    url = (BLUESKY_PDS + "/xrpc/app.bsky.feed.searchPosts?"
           + urllib.parse.urlencode({"q": q, "limit": limit, "sort": "latest"}))
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {jwt}",
                                               "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read()).get("posts", [])


BSKY_QUERIES = [
    ("NY", "homelessness New York"),
    ("NY", "foster care New York"),
    ("CA", "homelessness California"),
    ("CA", "eviction California"),
    ("VA", "foster care Virginia"),
    ("VA", "homelessness Virginia"),
]

bsky_rows = []
if BSKY_HANDLE and BSKY_APP_PW:
    try:
        jwt = bsky_login(BSKY_HANDLE, BSKY_APP_PW)
        print(f"Bluesky session OK for @{BSKY_HANDLE}")
        for region, q in BSKY_QUERIES:
            try:
                posts = bsky_search(jwt, q, limit=25)
                for p in posts:
                    rec = p.get("record", {}) or {}
                    handle = p.get("author", {}).get("handle", "")
                    rkey = (p.get("uri", "") or "").rsplit("/", 1)[-1]
                    text = rec.get("text", "") or ""
                    bsky_rows.append({
                        "source": "Bluesky", "region": region, "bias": "mixed",
                        "title": text.replace("\n", " ")[:80],
                        "date": (rec.get("createdAt") or "")[:16].replace("T", " "),
                        "when_dt": parse_when(rec.get("createdAt")),
                        "relevant": "★",  # matched a social-need query by construction
                        "url": f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else "",
                        "content": text,
                        "content_chars": len(text),
                        "extract_method": "bluesky:post",
                        "source_type": "social",
                    })
                print(f"  [{region}] '{q}' → {len(posts)} posts")
            except Exception as e:
                print(f"  [{region}] '{q}' FAIL {type(e).__name__}: {e}")
    except urllib.error.HTTPError as he:
        print(f"Bluesky login FAILED (HTTP {he.code}) — check bluesky_handle / bluesky_app_password. "
              f"{he.read()[:200].decode('utf-8', 'replace')}")
    except Exception as e:
        print(f"Bluesky login FAILED: {type(e).__name__}: {e}")
else:
    print("Skipping Bluesky — secrets bluesky_handle / bluesky_app_password not set.")

bsky_df = pd.DataFrame(bsky_rows)
if not bsky_df.empty:
    bsky_df = bsky_df.drop_duplicates(subset=["url"]).sort_values(
        "when_dt", ascending=False, na_position="last")
    print(f"\nBluesky: {len(bsky_df)} unique posts across {bsky_df['region'].nunique()} regions.")
    display(bsky_df[["date", "region", "content", "url"]])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1e. Government — policy, agendas & laws (keyless, `source_type=government`)
# MAGIC Authoritative, politically neutral sources:
# MAGIC - **Legistar** city-council API (keyless for these clients): recent **legislation/laws**
# MAGIC   (matters) + **meeting agendas** — San Francisco, Oakland & San Jose (CA), Richmond &
# MAGIC   Alexandria (VA). (SF is laws-only; its /events endpoint is misconfigured server-side.)
# MAGIC   Meetings are filtered to those with a published **agenda or minutes** within a
# MAGIC   **±45-day window** around today (`EVENT_LOOKBACK_DAYS` / `EVENT_LOOKAHEAD_DAYS`); each
# MAGIC   **agenda + minutes PDF is downloaded and text-extracted** into `content` (via `pypdf`),
# MAGIC   tagged `legistar:agenda+minutes`.
# MAGIC - **Federal Register API**: federal rules/notices searched per region+topic — abstract as
# MAGIC   content, official citation URL. Covers **NY** (no keyless NYC Legistar; NYC needs a token).
# MAGIC - **California Governor** press releases via **Google News `site:gov.ca.gov`** (gov.ca.gov
# MAGIC   directly IP-blocks Databricks; Google News is reachable and indexes the official releases —
# MAGIC   title + snippet + official link, card-free).
# MAGIC
# MAGIC All tagged `source_type=government`, `bias=neutral (official)`.

# COMMAND ----------

def legistar_get(client, endpoint, params, timeout=30):
    url = f"https://webapi.legistar.com/v1/{client}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


_MAX_YEAR = datetime.now(timezone.utc).year + 1

def gov_when(s):
    """parse_when but clamp absurd/dirty dates (Legistar has some year-9859 rows)."""
    dt = parse_when(s)
    if dt and (dt.year > _MAX_YEAR or dt.year < 1990):
        return None
    return dt


# (region, city, client, pull_events) — pull_events=False where the client's Legistar
# /events endpoint is misconfigured (SF returns HTTP 400), so we take laws only there.
LEGISTAR_CLIENTS = [
    ("CA", "San Francisco", "sfgov",      False),  # events endpoint 400s on SF's instance
    ("CA", "Oakland",       "oakland",    True),
    ("CA", "San Jose",      "sanjose",    True),
    ("VA", "Richmond",      "richmondva", True),
    ("VA", "Alexandria",    "alexandria", True),
]

# Meetings with a published agenda or minutes, within a symmetric window around today
# (±45 days ≈ 6 weeks back and forward). Ordering by EventDate alone would grab only the
# furthest-future meetings and miss these.
EVENT_LOOKBACK_DAYS = 45
EVENT_LOOKAHEAD_DAYS = 45
EVENT_TOP = 60
_now = datetime.now(timezone.utc)
_event_from = (_now - timedelta(days=EVENT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
_event_to = (_now + timedelta(days=EVENT_LOOKAHEAD_DAYS + 1)).strftime("%Y-%m-%d")  # exclusive upper bound

gov_rows = []

# --- Legistar: laws (matters) + agendas (events) ---
for region, city, client, pull_events in LEGISTAR_CLIENTS:
    # Laws / legislation
    try:
        matters = legistar_get(client, "matters",
                               {"$top": 6, "$orderby": "MatterIntroDate desc"})
        for m in matters:
            title = m.get("MatterName") or m.get("MatterFile") or "(untitled)"
            body = m.get("MatterTitle") or ""   # long legislative summary → content
            mid, guid = m.get("MatterId"), m.get("MatterGuid")
            url = (f"https://{client}.legistar.com/LegislationDetail.aspx?ID={mid}&GUID={guid}"
                   if mid and guid else "")
            gov_rows.append({
                "source": f"{city} Council (Legistar)", "region": region,
                "bias": "neutral (official)",
                "title": f"{m.get('MatterFile','')}: {title}".strip(": "),
                "date": (m.get("MatterIntroDate") or "")[:10],
                "when_dt": gov_when(m.get("MatterIntroDate")),
                "relevant": "★" if any(k in (title + " " + body).lower() for k in KEYWORDS) else "",
                "url": url, "content": body, "content_chars": len(body),
                "extract_method": "legistar:matter", "source_type": "government",
            })
        print(f"OK  {city} laws: {len(matters)}")
    except Exception as e:
        print(f"--  {city} laws FAIL: {type(e).__name__} {getattr(e,'code','')}")
    # Meeting agendas + minutes (skip clients whose /events endpoint is misconfigured)
    if not pull_events:
        continue
    try:
        events = legistar_get(client, "events", {
            "$filter": ("(EventAgendaFile ne null or EventMinutesFile ne null) "
                        f"and EventDate ge datetime'{_event_from}' "
                        f"and EventDate lt datetime'{_event_to}'"),
            "$top": EVENT_TOP, "$orderby": "EventDate desc"})
        n_docs = 0
        for ev in events:
            body_name = ev.get("EventBodyName") or "Meeting"
            ev_date = (ev.get("EventDate") or "")[:10]
            url = ev.get("EventInSiteURL") or ev.get("EventAgendaFile") or ""
            # Pull agenda AND minutes PDFs (when present) and concatenate their text into content.
            parts, got = [], []
            for label, furl in [("agenda", ev.get("EventAgendaFile")),
                                ("minutes", ev.get("EventMinutesFile"))]:
                if not furl:
                    continue
                try:
                    _, pdf_bytes = fetch(furl, timeout=30, accept="application/pdf,*/*")
                    pdf_text = extract_pdf_text(pdf_bytes)
                    if len(pdf_text) >= 100:
                        parts.append(f"=== {label.upper()} ===\n{pdf_text}")
                        got.append(label)
                except Exception:
                    pass  # missing/scanned/failed doc → just skip that part
            if parts:
                content = "\n\n".join(parts)
                method = "legistar:" + "+".join(got)  # e.g. legistar:agenda+minutes
                n_docs += 1
            else:
                content = f"{body_name} meeting ({ev_date})."
                method = "legistar:event(no-doc-text)"
            gov_rows.append({
                "source": f"{city} Council (Legistar)", "region": region,
                "bias": "neutral (official)",
                "title": f"Meeting — {body_name} ({ev_date})",
                "date": ev_date,
                "when_dt": gov_when(ev.get("EventDate")),
                "relevant": "★" if any(k in content.lower() for k in KEYWORDS) else "",
                "url": url, "content": content,
                "content_chars": len(content),
                "extract_method": method, "source_type": "government",
            })
        print(f"OK  {city} meetings: {len(events)} ({n_docs} with agenda/minutes text)")
    except Exception as e:
        print(f"--  {city} meetings FAIL: {type(e).__name__} {getattr(e,'code','')}")

# --- Federal Register: federal policy per region+topic (covers NY) ---
FR_QUERIES = [
    ("NY", "homelessness OR foster care New York"),
    ("CA", "homelessness OR housing California"),
    ("VA", "foster care OR child welfare Virginia"),
]
for region, term in FR_QUERIES:
    try:
        d = json.loads(fetch(
            "https://www.federalregister.gov/api/v1/documents.json?"
            + urllib.parse.urlencode({"conditions[term]": term, "per_page": 10, "order": "newest"}),
            accept="application/json")[1])
        for r in d.get("results", []):
            abstract = r.get("abstract") or ""
            agency = (r.get("agencies") or [{}])[0].get("name", "")
            gov_rows.append({
                "source": f"Federal Register ({agency})" if agency else "Federal Register",
                "region": region, "bias": "neutral (official)",
                "title": f"[{r.get('type','')}] {r.get('title','')}",
                "date": r.get("publication_date", ""),
                "when_dt": gov_when(r.get("publication_date")),
                "relevant": "★" if any(k in (r.get("title","")+abstract).lower() for k in KEYWORDS) else "",
                "url": r.get("html_url", ""), "content": abstract,
                "content_chars": len(abstract),
                "extract_method": "federalregister:abstract", "source_type": "government",
            })
        print(f"OK  Federal Register [{region}]: {len(d.get('results', []))}")
    except Exception as e:
        print(f"--  Federal Register [{region}] FAIL: {type(e).__name__}: {e}")

# --- California Governor press releases via Google News ---
# gov.ca.gov's Cloudflare intermittently 403s Databricks egress IPs, so we can't fetch its RSS
# directly. Google News (reachable from Databricks) indexes the official CA.gov press releases;
# a site:gov.ca.gov query surfaces them with title + snippet + the official link. Full body text
# would require Bright Data (the page itself is IP-blocked); snippet is what we get card-free.
try:
    _gn_url = ("https://news.google.com/rss/search?"
               + urllib.parse.urlencode({"q": "site:gov.ca.gov", "hl": "en-US",
                                         "gl": "US", "ceid": "US:en"}))
    _, gbody = fetch(_gn_url, accept="application/rss+xml, application/xml, */*")
    n_gov = 0
    for it in parse_feed(gbody, max_items=12):
        snippet = html_to_text(it.get("summary", "")) or (it["title"] or "")
        gov_rows.append({
            "source": "California Governor (via Google News)", "region": "CA",
            "bias": "neutral (official)",
            "title": it["title"] or "",
            "date": it["when_dt"].strftime("%Y-%m-%d") if it["when_dt"] else "",
            "when_dt": it["when_dt"],
            "relevant": "★" if any(k in (it["title"] or "").lower() for k in KEYWORDS) else "",
            "url": it["link"] or "", "content": snippet, "content_chars": len(snippet),
            "extract_method": "gov-google-news:gov.ca.gov", "source_type": "government",
        })
        n_gov += 1
    print(f"OK  California Governor (Google News site:gov.ca.gov): {n_gov}")
except Exception as e:
    print(f"--  California Governor (Google News) FAIL: {type(e).__name__}: {e}")

gov_df = pd.DataFrame(gov_rows)
if not gov_df.empty:
    gov_df = gov_df.sort_values("when_dt", ascending=False, na_position="last")
    print(f"\nGovernment: {len(gov_df)} records "
          f"({gov_df['content_chars'].gt(0).sum()} with body content).")
    display(gov_df[["date", "source", "region", "relevant", "title", "content_chars", "url"]])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Weather alerts — api.weather.gov (keyless)
# MAGIC Active National Weather Service alerts per state → shelter / relocation demand signal.

# COMMAND ----------

wx_rows = []
for st in ["NY", "CA", "VA"]:
    try:
        code, body = fetch(f"https://api.weather.gov/alerts/active?area={st}",
                           accept="application/geo+json")
        data = json.loads(body)
        feats = data.get("features", [])
        for f in feats[:10]:
            p = f.get("properties", {})
            wx_rows.append({
                "source": "NWS api.weather.gov",
                "region": st,
                "title": p.get("event", ""),
                "headline": (p.get("headline") or "")[:120],
                "date": p.get("sent", ""),
                "severity": p.get("severity", ""),
                "url": p.get("id", ""),
                "source_type": "weather",
            })
        print(f"{st}: {len(feats)} active alerts (showing up to 10)")
    except Exception as e:
        print(f"{st}: FAIL {type(e).__name__}: {e}")

wx_df = pd.DataFrame(wx_rows)
if not wx_df.empty:
    display(wx_df[["date", "region", "title", "severity", "headline"]])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Disaster declarations — OpenFEMA (keyless)
# MAGIC Most recent federal disaster declarations per state → acute family-displacement signal.

# COMMAND ----------

fema_rows = []
base = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
for st in ["NY", "CA", "VA"]:
    q = {"$filter": f"state eq '{st}'", "$top": "5", "$orderby": "declarationDate desc"}
    url = base + "?" + urllib.parse.urlencode(q)
    try:
        code, body = fetch(url)
        data = json.loads(body)
        recs = data.get("DisasterDeclarationsSummaries", [])
        for r in recs:
            dnum = r.get("disasterNumber", "")
            area = r.get("designatedArea", "")
            # Real citation URL; county appended as a fragment so per-county rows stay distinct
            fema_url = f"https://www.fema.gov/disaster/{dnum}" + (
                "#" + urllib.parse.quote(str(area)) if area else "")
            fema_rows.append({
                "source": "OpenFEMA",
                "region": st,
                "title": r.get("declarationTitle", ""),
                "type": r.get("incidentType", ""),
                "date": (r.get("declarationDate") or "")[:10],
                "county": area,
                "url": fema_url,
                "source_type": "disaster",
            })
        print(f"{st}: {len(recs)} recent declarations")
    except Exception as e:
        print(f"{st}: FAIL {type(e).__name__}: {e}")

fema_df = pd.DataFrame(fema_rows)
if not fema_df.empty:
    display(fema_df[["date", "region", "type", "title", "county"]])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Combined normalized preview
# MAGIC One shape across all sources: `source, region, source_type, title, date, url`.
# MAGIC This is the schema we'd land as the bronze `bronze_tmp_raw_issues` table later.

# COMMAND ----------

COLS = ["source", "region", "source_type", "bias", "title", "date", "url", "content"]

frames = []
if not news_df.empty:
    nf = news_df.copy()
    if "content" not in nf.columns:
        nf["content"] = ""
    frames.append(nf[COLS])
if not bright_df.empty:
    bf = bright_df.copy()
    if "content" not in bf.columns:
        bf["content"] = ""
    frames.append(bf[COLS])
if not gnews_df.empty:
    frames.append(gnews_df.assign(content="")[COLS])
if not bsky_df.empty:
    frames.append(bsky_df[COLS])
if not gov_df.empty:
    frames.append(gov_df[COLS])
if not wx_df.empty:
    frames.append(wx_df.assign(bias="neutral (official)", content=wx_df["headline"])[COLS])
if not fema_df.empty:
    frames.append(fema_df.assign(bias="neutral (official)", content="")[COLS])

if frames:
    combined = pd.concat(frames, ignore_index=True)
    print(f"Combined preview: {len(combined)} records across {combined['source'].nunique()} sources.")
    display(combined)
else:
    combined = pd.DataFrame(columns=COLS)
    print("Nothing retrieved. Check network egress from this workspace/compute.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Persist to bronze — idempotent upsert (safe for a daily job)
# MAGIC MERGEs this run into `ai_fde_hackathon_catalog.brickhearts.bronze_tmp_raw_issues` keyed on the
# MAGIC **`url`** (the primary id; a synthesized `brickhearts://…` id fills in for any URL-less row):
# MAGIC - **No duplicates** — re-running the same day, or catching an article that's still in the
# MAGIC   feed tomorrow, updates the existing row (refreshes `content`, bumps `last_seen_at`)
# MAGIC   instead of inserting a copy. Within-run duplicates (same URL from >1 source) are collapsed first.
# MAGIC - **Miss risk** is reduced by larger fetch caps, but a source that publishes more than its
# MAGIC   cap between runs can still roll off before capture — run daily (or more often) and raise
# MAGIC   the caps / add pagination for very high-volume sources. `first_seen_at` lets you audit gaps.
# MAGIC
# MAGIC Set `PERSIST = False` for a display-only dry run.

# COMMAND ----------

from pyspark.sql import functions as F

PERSIST = True
CATALOG, SCHEMA, TABLE = "ai_fde_hackathon_catalog", "brickhearts", "bronze_raw_issues"
FQN = f"{CATALOG}.{SCHEMA}.{TABLE}"

# The URL is the primary key. Column order defines the expected table schema (used by self-heal).
PERSIST_COLS = ["url", "source", "region", "source_type", "bias", "title", "date", "content"]

if PERSIST and not combined.empty:
    src = combined.copy()
    src["url"] = src["url"].fillna("").astype(str).str.strip()
    # Safety net: no row may have an empty key. Synthesize a stable URL-shaped id if one is missing.
    missing = src["url"] == ""
    src.loc[missing, "url"] = (
        "brickhearts://" + src.loc[missing, "source"].astype(str) + "/"
        + src.loc[missing, "title"].astype(str).str.slice(0, 80) + "|"
        + src.loc[missing, "date"].astype(str))
    src["content"] = src["content"].fillna("").astype(str)
    src["_clen"] = src["content"].str.len()
    # within-run dedup: same url from >1 source/query → keep the richest-content copy
    src = (src.sort_values("_clen", ascending=False)
              .drop_duplicates(subset=["url"], keep="first"))
    print(f"{len(src)} unique URLs this run (deduped from {len(combined)} rows).")

    sdf = (spark.createDataFrame(src[PERSIST_COLS].fillna(""))
                .withColumn("run_ts", F.current_timestamp()))
    sdf.createOrReplaceTempView("updates")

    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
    # Self-heal: rebuild once if an existing table has a different schema (e.g. the earlier
    # hashed-issue_id or overwrite version). Fires only on mismatch — history is safe thereafter.
    expected = set(PERSIST_COLS) | {"first_seen_at", "last_seen_at"}
    if spark.catalog.tableExists(FQN):
        existing = {f.name for f in spark.table(FQN).schema.fields}
        if existing != expected:
            print(f"Existing {FQN} schema {sorted(existing)} != expected — rebuilding, keyed on url.")
            spark.sql(f"DROP TABLE {FQN}")
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {FQN} (
            url STRING, source STRING, region STRING, source_type STRING, bias STRING,
            title STRING, `date` STRING, content STRING,
            first_seen_at TIMESTAMP, last_seen_at TIMESTAMP
        ) USING DELTA
    """)

    before = spark.table(FQN).count()
    spark.sql(f"""
        MERGE INTO {FQN} t
        USING updates s ON t.url = s.url
        WHEN MATCHED THEN UPDATE SET
            t.last_seen_at = s.run_ts, t.content = s.content, t.title = s.title,
            t.`date` = s.`date`, t.region = s.region,
            t.source_type = s.source_type, t.bias = s.bias, t.source = s.source
        WHEN NOT MATCHED THEN INSERT
            (url, source, region, source_type, bias, title, `date`, content,
             first_seen_at, last_seen_at)
            VALUES (s.url, s.source, s.region, s.source_type, s.bias, s.title, s.`date`,
                    s.content, s.run_ts, s.run_ts)
    """)
    after = spark.table(FQN).count()
    print(f"{FQN}: {before} → {after} rows  (+{after - before} new, "
          f"{len(src) - (after - before)} updated/seen-again).")
    display(spark.sql(f"""
        SELECT source_type, count(*) AS rows, min(first_seen_at) AS first_seen,
               max(last_seen_at) AS last_seen
        FROM {FQN} GROUP BY source_type ORDER BY rows DESC
    """))
elif not PERSIST:
    print("PERSIST=False — display-only dry run, nothing written.")
else:
    print("No combined data to persist.")

# COMMAND ----------

display(combined)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Notes & next steps
# MAGIC - **Egress:** this needs outbound internet from the compute. If every source FAILs with a
# MAGIC   timeout, the cluster likely has no public internet egress — try serverless, or route
# MAGIC   fetches through a proxy / Bright Data.
# MAGIC - **RSS is only the free tier.** For paywalled majors (LA Times, SF Chronicle, Newsday)
# MAGIC   use Bright Data. For legislation, add the Plural Policy API (all 3 states uniformly).
# MAGIC - **Next:** land `combined` as `ai_fde_hackathon_catalog.brickhearts.bronze_tmp_raw_issues` (bronze),
# MAGIC   then add NER + relevance/citation scoring per the project data model.