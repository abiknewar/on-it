#!/usr/bin/env python3
"""
On It — daily brief crawler.

Goal: the crazy-interesting, world-changing things that are trending right now —
what people are actually searching for and reading today.

Free, no-API-key sources (both work from GitHub Actions):
  1. Wikipedia most-viewed articles  -> what the world is looking up today,
     with real view counts, enriched with each topic's summary.
  2. Google News "Top Stories" RSS   -> the biggest headlines of the day.

Results are interleaved so you get both "what people are searching" and the
"big story" headlines. Standard library only — no pip install for this script.
"""

import json
import re
import html
import hashlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Google News regions to pull top stories from.
NEWS_GEOS = [("US", "en-US", "US:en"), ("IN", "en-IN", "IN:en")]

TARGET_TOTAL = 20
WIKI_MAX = 13
NEWS_MAX = 12

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Wikipedia pages that aren't real "topics".
WIKI_SKIP = {"Main_Page", "-", "Special:Search", "Wikipedia:Featured_pictures"}

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "briefs.json"


# ---------------------------------------------------------------------------
# HTTP + text helpers
# ---------------------------------------------------------------------------

def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _get_json(url, timeout=25):
    return json.loads(_get(url, timeout=timeout))


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _domain(url):
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def _human(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


# ---------------------------------------------------------------------------
# Source 1: Wikipedia most-viewed (what people are searching / looking up)
# ---------------------------------------------------------------------------

def from_wikipedia():
    items = []
    # yesterday (UTC) — today's ranking isn't finalised yet
    day = datetime.now(timezone.utc) - timedelta(days=1)
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
           f"en.wikipedia/all-access/{day:%Y/%m/%d}")
    try:
        data = _get_json(url)
        articles = data["items"][0]["articles"]
    except Exception as e:
        print(f"  [Wikipedia] skipped: {e}")
        return items

    for a in articles:
        name = a.get("article", "")
        if not name or name in WIKI_SKIP or ":" in name:
            continue
        title = name.replace("_", " ")
        views = int(a.get("views", 0))
        page_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(name)

        summary, thumb = _wiki_summary(name)
        items.append({
            "title": title,
            "summary": summary or f"{views:,} people looked this up today — it's trending on Wikipedia.",
            "url": page_url,
            "trend": title,
            "source": "Wikipedia · most viewed",
            "badge": f"{_human(views)} views",
            "engagement": f"{views:,} views today",
            "picture": thumb,
            "published": datetime.now(timezone.utc).isoformat(),
            "score": views,
            "kind": "search",
        })
        if len(items) >= WIKI_MAX:
            break
    return items


def _wiki_summary(name):
    """Short human summary + thumbnail for a Wikipedia article (best-effort)."""
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(name)
        d = _get_json(url, timeout=12)
        extract = _clean(d.get("extract", ""))[:280]
        thumb = (d.get("thumbnail") or {}).get("source", "")
        return extract, thumb
    except Exception:
        return "", ""


# ---------------------------------------------------------------------------
# Source 2: Google News top stories (the big headlines of the day)
# ---------------------------------------------------------------------------

def from_google_news_top(geo, hl, ceid):
    items = []
    url = f"https://news.google.com/rss?hl={hl}&gl={geo}&ceid={ceid}"
    try:
        root = ET.fromstring(_get(url))
    except Exception as e:
        print(f"  [News/{geo}] skipped: {e}")
        return items

    for i, it in enumerate(root.iter("item")):
        title = _clean(it.findtext("title"))
        if not title:
            continue
        src = ""
        if " - " in title:
            title, src = title.rsplit(" - ", 1)
        link = (it.findtext("link") or "").strip()
        desc = _clean(it.findtext("description"))
        items.append({
            "title": title,
            "summary": desc[:280] or f"{title} — a top story today.",
            "url": link,
            "trend": "",
            "source": f"Top story · {src}" if src else "Top story",
            "badge": "Top story",
            "engagement": src or "Top story",
            "picture": "",
            "published": datetime.now(timezone.utc).isoformat(),
            # high, order-preserving score so the freshest top stories lead
            "score": 5_000_000 - i * 1000,
            "kind": "news",
        })
        if len(items) >= NEWS_MAX:
            break
    return items


# ---------------------------------------------------------------------------
# De-dup + merge
# ---------------------------------------------------------------------------

_STOP = {"the", "a", "an", "to", "of", "in", "on", "for", "and", "with",
         "is", "as", "at", "by", "its", "this", "that", "new", "how"}


def _tokens(title):
    return {w for w in re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
            if w not in _STOP and len(w) > 2}


def dedupe(items):
    kept = []
    for it in sorted(items, key=lambda x: x["score"], reverse=True):
        toks = _tokens(it["title"])
        if not toks:
            continue
        dup = False
        for k in kept:
            inter = len(toks & k["_toks"])
            union = len(toks | k["_toks"]) or 1
            smaller = min(len(toks), len(k["_toks"])) or 1
            if inter / union >= 0.6 or (inter >= 4 and inter / smaller >= 0.8):
                dup = True
                break
        if not dup:
            it["_toks"] = toks
            kept.append(it)
    for it in kept:
        it.pop("_toks", None)
    return kept


def interleave(a, b, n):
    """Alternate items from two lists so neither source dominates the feed."""
    out, i, j = [], 0, 0
    while len(out) < n and (i < len(a) or j < len(b)):
        if i < len(a):
            out.append(a[i]); i += 1
        if j < len(b) and len(out) < n:
            out.append(b[j]); j += 1
    return out


def finalize(items):
    for it in items:
        it["id"] = hashlib.sha1((it["url"] or it["title"]).encode("utf-8")).hexdigest()[:12]
        it["domain"] = _domain(it["url"])
    return items


def main():
    now = datetime.now(timezone.utc)

    print("Gathering what people are searching (Wikipedia)…")
    wiki = from_wikipedia()
    print(f"  {len(wiki)} trending topics.")

    print("Gathering top stories (Google News)…")
    news = []
    for geo, hl, ceid in NEWS_GEOS:
        news += from_google_news_top(geo, hl, ceid)
    print(f"  {len(news)} top stories.")

    wiki = dedupe(wiki)
    news = dedupe(news)
    # dedupe news against wiki topics too
    merged = dedupe(wiki + news)
    wiki_only = [x for x in merged if x.get("kind") == "search"]
    news_only = [x for x in merged if x.get("kind") == "news"]

    briefs = finalize(interleave(wiki_only, news_only, TARGET_TOTAL))
    print(f"{len(briefs)} briefs selected.")

    payload = {
        "generated_at": now.isoformat(),
        "date_label": now.strftime("%A, %d %B %Y"),
        "source_label": "Trending — what the world is searching",
        "count": len(briefs),
        "briefs": briefs,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
