#!/usr/bin/env python3
"""
On It — daily brief crawler.

Source: Google Trends "daily trending searches" (free, no API key) — i.e.
what people are actually searching for right now. Each trend comes with the
top news headline, a snippet, and an approximate search volume, which we turn
into a readable, rankable brief.

Only the Python standard library is used, so the GitHub Action needs no
`pip install` step for this script.
"""

import json
import re
import html
import hashlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# Which Google Trends regions to pull. US surfaces the big global / world-
# changing stories; IN adds what's blowing up locally. Merged and de-duped.
GEOS = ["US", "IN"]

TARGET_TOTAL = 20

# A browser-like User-Agent — Google serves cleaner responses to these.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "briefs.json"


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


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


def _traffic_to_int(s):
    """'200,000+' -> 200000 ; '2M+' -> 2000000."""
    if not s:
        return 0
    s = s.strip().upper().replace(",", "").replace("+", "")
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except Exception:
        return 0


def _locals(elem, localname):
    """All descendants whose tag local-name matches, ignoring XML namespace."""
    return [e for e in elem.iter() if e.tag.rsplit("}", 1)[-1] == localname]


def _local_text(elem, localname):
    for e in _locals(elem, localname):
        if e.text and e.text.strip():
            return _clean(e.text)
    return ""


def from_google_trends(geo):
    """Trending searches for a region.

    Google has shipped several RSS shapes/namespaces for trends, so we try the
    current "Trending Now" endpoint first, fall back to the older daily feed,
    and parse fields by local tag name (namespace-agnostic) to survive changes.
    """
    items = []
    endpoints = [
        f"https://trends.google.com/trending/rss?geo={geo}",
        f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}",
    ]
    root = None
    for url in endpoints:
        try:
            candidate = ET.fromstring(_get(url))
            if list(candidate.iter("item")):
                root = candidate
                break
        except Exception as e:
            print(f"  [Trends/{geo}] {url.split('?')[0]} failed: {e}")
    if root is None:
        print(f"  [Trends/{geo}] no items from any endpoint")
        return items

    for it in root.iter("item"):
        term = _local_text(it, "title")
        if not term:
            continue
        traffic_raw = _local_text(it, "approx_traffic")

        headline = _local_text(it, "news_item_title")
        snippet = _local_text(it, "news_item_snippet")
        links = _locals(it, "news_item_url")
        link = next((e.text.strip() for e in links if e.text and e.text.strip()), "")
        src = _local_text(it, "news_item_source")
        picture = _local_text(it, "news_item_picture") or _local_text(it, "picture")

        title = headline or term
        if not link:
            link = "https://www.google.com/search?q=" + urllib.parse.quote(term)

        items.append({
            "title": title,
            "summary": snippet or f"“{term}” is trending in search right now.",
            "url": link,
            "trend": term,
            "source": src or "Google Trends",
            "traffic": traffic_raw,
            "engagement": f"{traffic_raw} searches" if traffic_raw else "Trending in search",
            "geo": geo,
            "picture": picture,
            "published": datetime.now(timezone.utc).isoformat(),
            "score": _traffic_to_int(traffic_raw) or 1,
        })
    return items


# ---------------------------------------------------------------------------
# De-dup + finalize
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


def finalize(items):
    out = []
    for it in items:
        it["id"] = hashlib.sha1((it["url"] or it["title"]).encode("utf-8")).hexdigest()[:12]
        it["domain"] = _domain(it["url"])
        out.append(it)
    return out


def main():
    now = datetime.now(timezone.utc)

    raw = []
    for geo in GEOS:
        print(f"[{geo}] gathering trending searches…")
        raw += from_google_trends(geo)

    print(f"Collected {len(raw)} raw trends.")
    deduped = dedupe(raw)
    deduped.sort(key=lambda x: x["score"], reverse=True)
    briefs = finalize(deduped[:TARGET_TOTAL])
    print(f"{len(briefs)} briefs selected.")

    payload = {
        "generated_at": now.isoformat(),
        "date_label": now.strftime("%A, %d %B %Y"),
        "source_label": "Trending on search",
        "count": len(briefs),
        "briefs": briefs,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
