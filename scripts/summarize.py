#!/usr/bin/env python3
"""
Turn each trending topic's recent-news context into a clear paragraph
explaining WHAT is happening and WHY it's trending — using GitHub Models
(free for GitHub users, called from the Action with the built-in token,
no external API key).

Reads data/briefs.json (each brief has a `context` list from fetch_briefs.py),
rewrites `summary` with the AI paragraph, and drops `context`. If the AI is
unavailable, the fallback summary from fetch_briefs.py is kept as-is.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

BRIEFS = Path(__file__).resolve().parent.parent / "data" / "briefs.json"

# GitHub Models — free inference for GitHub users.
ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODEL = "openai/gpt-4o-mini"

SYSTEM = ("You are a sharp news editor writing a daily brief. You write clear, "
          "factual, engaging paragraphs. You never invent facts.")


def summarize(topic, ctx, token):
    headlines = "\n".join(
        f"- {c['title']}" + (f" — {c['snippet']}" if c.get("snippet") else "")
        + (f" (via {c['source']})" if c.get("source") else "")
        for c in ctx
    )
    user = (
        f'Topic trending today: "{topic}".\n\n'
        "Using ONLY the recent headlines below, write ONE engaging paragraph "
        "(4 to 6 sentences) that explains what is happening and why this is "
        "trending right now — the kind of context someone needs to actually "
        "understand it. Be specific and factual. Do not invent anything. Do "
        "not start with 'This topic' or repeat the topic name mechanically.\n\n"
        f"Recent headlines:\n{headlines}"
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": 260,
    }).encode()

    req = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def main():
    data = json.loads(BRIEFS.read_text())
    briefs = data.get("briefs", [])
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

    ai_used = 0
    for b in briefs:
        ctx = b.pop("context", [])
        if not token or not ctx:
            continue
        topic = b.get("trend") or b.get("title") or ""
        try:
            para = summarize(topic, ctx, token)
            if para and len(para) > 40:
                b["summary"] = para
                ai_used += 1
        except Exception as e:
            print(f"  [AI/{topic[:30]}] fell back: {e}", file=sys.stderr)

    data["ai_summarized"] = ai_used > 0
    BRIEFS.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"AI-summarized {ai_used}/{len(briefs)} briefs "
          f"({'GitHub Models' if ai_used else 'fallback headlines only'}).")


if __name__ == "__main__":
    main()
