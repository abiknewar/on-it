#!/usr/bin/env python3
"""
On It — daily brief crawler.

Pulls *trending* items from free, no-auth sources across the configured
interests (AI, Design, Marketing, Tech), ranks them, de-duplicates, and
writes the top items to data/briefs.json.

Sources (all free, no API keys):
  - Hacker News   (Algolia HN Search API)   -> points-ranked stories
  - Reddit        (public /top.json?t=day)   -> upvote-ranked posts
  - Google News   (RSS search, when:1d)      -> fresh news per interest

Only the Python standard library is used, so the GitHub Action needs no
`pip install` step.
"""

import json
import re
import html
import hashlib
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration: your interests and where to look for each one.
# ---------------------------------------------------------------------------

INTERESTS = {
    "AI": {
        "emoji": "🤖",
        "hn_query": "AI OR LLM OR OpenAI OR Anthropic OR \"machine learning\"",
        "subreddits": ["artificial", "MachineLearning", "OpenAI", "LocalLLaMA", "singularity"],
        "news_query": "artificial intelligence OR AI launch OR LLM",
    },
    "Design": {
        "emoji": "🎨",
        "hn_query": "design OR UX OR Figma OR typography",
        "subreddits": ["Design", "web_design", "userexperience", "graphic_design"],
        "news_query": "design tool OR UX design OR product design",
    },
    "Marketing": {
        "emoji": "📈",
        "hn_query": "marketing OR growth OR advertising OR SEO",
        "subreddits": ["marketing", "DigitalMarketing", "SEO", "Entrepreneur"],
        "news_query": "marketing OR growth marketing OR advertising campaign",
    },
    "Tech": {
        "emoji": "💻",
        "hn_query": "launch OR release OR startup OR product",
        "subreddits": ["technology", "gadgets", "programming", "technews"],
        "news_query": "tech launch OR new gadget OR startup funding",
    },
}

# How many briefs to keep in the final feed, and per source caps.
TARGET_TOTAL = 20
MAX_PER_CATEGORY = 7

# Politeness: identify ourselves so Reddit / news servers don't 429 us.
USER_AGENT = "on-it-daily-brief/1.0 (personal reader; +https://github.com/abiknewar/on-it)"

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "briefs.json"


# ---------------------------------------------------------------------------
# Small HTTP helper with graceful failure — one dead source must not kill the run.
# ---------------------------------------------------------------------------

def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _get_json(url, timeout=25):
    return json.loads(_get(url, timeout=timeout))


def _clean(text):
    """Strip HTML tags/entities and collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _domain(url):
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def from_hacker_news(category, cfg, since_ts):
    """Trending HN stories for this interest (ranked by points)."""
    items = []
    q = urllib.parse.quote(cfg["hn_query"])
    url = (
        "https://hn.algolia.com/api/v1/search"
        f"?query={q}&tags=story&numericFilters=created_at_i>{since_ts},points>20"
        "&hitsPerPage=25"
    )
    try:
        data = _get_json(url)
    except Exception as e:
        print(f"  [HN/{category}] skipped: {e}")
        return items

    for hit in data.get("hits", []):
        title = _clean(hit.get("title"))
        if not title:
            continue
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        points = hit.get("points", 0) or 0
        comments = hit.get("num_comments", 0) or 0
        items.append({
            "title": title,
            "summary": _clean(hit.get("story_text"))[:280],
            "url": story_url,
            "source": "Hacker News",
            "category": category,
            "published": _iso_from_ts(hit.get("created_at_i")),
            # points weigh more than comments for "how big is this"
            "score": points + comments * 0.5,
            "engagement": f"{points} points · {comments} comments",
        })
    return items


def from_reddit(category, cfg, since_ts):
    """Top-of-day Reddit posts across this interest's subreddits."""
    items = []
    for sub in cfg["subreddits"]:
        url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit=15"
        try:
            data = _get_json(url)
        except Exception as e:
            print(f"  [Reddit/r/{sub}] skipped: {e}")
            continue
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            if p.get("stickied") or p.get("over_18"):
                continue
            title = _clean(p.get("title"))
            if not title:
                continue
            ups = p.get("ups", 0) or 0
            comments = p.get("num_comments", 0) or 0
            # link posts point outward; self posts point to the discussion
            link = p.get("url_overridden_by_dest") or p.get("url") or ""
            if not link or link.startswith("/"):
                link = "https://www.reddit.com" + p.get("permalink", "")
            items.append({
                "title": title,
                "summary": _clean(p.get("selftext"))[:280],
                "url": link,
                "source": f"Reddit · r/{sub}",
                "category": category,
                "published": _iso_from_ts(p.get("created_utc")),
                # reddit vote counts are large; scale down to sit near HN points
                "score": ups * 0.05 + comments * 0.2,
                "engagement": f"{ups:,} upvotes · {comments} comments",
            })
    return items


def from_google_news(category, cfg, since_ts):
    """Fresh news items (last day) for this interest via Google News RSS."""
    items = []
    q = urllib.parse.quote(cfg["news_query"] + " when:1d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        xml = _get(url)
        root = ET.fromstring(xml)
    except Exception as e:
        print(f"  [News/{category}] skipped: {e}")
        return items

    for item in root.iter("item"):
        title = _clean(item.findtext("title"))
        if not title:
            continue
        # Google News titles often trail with " - Source"; split it out.
        source_name = ""
        if " - " in title:
            title, source_name = title.rsplit(" - ", 1)
        link = (item.findtext("link") or "").strip()
        desc = _clean(item.findtext("description"))
        items.append({
            "title": title,
            "summary": desc[:280],
            "url": link,
            "source": f"News · {source_name}" if source_name else "Google News",
            "category": category,
            "published": _parse_rss_date(item.findtext("pubDate")),
            # news has no vote signal; give it a modest baseline so it can
            # surface when HN/Reddit are quiet, but sits below hot discussions.
            "score": 8,
            "engagement": "Fresh coverage",
        })
    return items


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _iso_from_ts(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _parse_rss_date(s):
    if not s:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s, fmt).astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Ranking & de-duplication
# ---------------------------------------------------------------------------

def _norm_title(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def dedupe(items):
    """Drop near-duplicate stories, keeping the highest-scored copy."""
    seen = {}
    for it in items:
        key = _norm_title(it["title"])[:60]
        if not key:
            continue
        if key not in seen or it["score"] > seen[key]["score"]:
            # merge engagement note if the same story came from two places
            if key in seen:
                it["also_seen"] = seen[key]["source"]
            seen[key] = it
    return list(seen.values())


def select(items):
    """Balance across categories, then fill remaining slots by score."""
    by_cat = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)

    chosen = []
    for cat, lst in by_cat.items():
        lst.sort(key=lambda x: x["score"], reverse=True)
        chosen.extend(lst[:MAX_PER_CATEGORY])

    # if we're short, backfill with the next-best leftovers
    if len(chosen) < TARGET_TOTAL:
        chosen_ids = {id(x) for x in chosen}
        leftovers = [x for x in items if id(x) not in chosen_ids]
        leftovers.sort(key=lambda x: x["score"], reverse=True)
        chosen.extend(leftovers[: TARGET_TOTAL - len(chosen)])

    chosen.sort(key=lambda x: x["score"], reverse=True)
    return chosen[:TARGET_TOTAL]


def finalize(items):
    """Add stable ids and a readable summary fallback."""
    out = []
    for it in items:
        raw_id = (it["url"] or it["title"]).encode("utf-8")
        it["id"] = hashlib.sha1(raw_id).hexdigest()[:12]
        if not it["summary"]:
            it["summary"] = f"{it['title']} — trending on {it['source']} today."
        it["domain"] = _domain(it["url"])
        # round score for cleaner JSON
        it["score"] = round(float(it["score"]), 1)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    now = datetime.now(timezone.utc)
    since_ts = int((now - timedelta(days=1)).timestamp())

    all_items = []
    for category, cfg in INTERESTS.items():
        print(f"[{category}] gathering…")
        all_items += from_hacker_news(category, cfg, since_ts)
        all_items += from_reddit(category, cfg, since_ts)
        all_items += from_google_news(category, cfg, since_ts)

    print(f"Collected {len(all_items)} raw items.")
    deduped = dedupe(all_items)
    print(f"{len(deduped)} after de-dupe.")
    selected = select(deduped)
    briefs = finalize(selected)
    print(f"{len(briefs)} briefs selected.")

    payload = {
        "generated_at": now.isoformat(),
        "date_label": now.strftime("%A, %d %B %Y"),
        "interests": [{"name": k, "emoji": v["emoji"]} for k, v in INTERESTS.items()],
        "count": len(briefs),
        "briefs": briefs,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
