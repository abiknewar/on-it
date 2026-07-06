#!/usr/bin/env python3
"""
Generate clean narration audio for the day's brief TITLES using edge-tts
(Microsoft Edge neural voices — free, no API key).

Reads data/briefs.json, speaks only the titles, and writes data/narration.mp3.
If anything fails (e.g. the TTS endpoint is unreachable), it exits 0 without
an MP3 so the site can fall back to the browser's built-in voice.
"""

import asyncio
import json
import sys
from pathlib import Path

# Clean Indian-English neural voice. Alternatives: en-IN-PrabhatNeural (male),
# en-US-AriaNeural, en-GB-SoniaNeural.
VOICE = "en-IN-NeerjaNeural"

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = ROOT / "data" / "briefs.json"
OUT = ROOT / "data" / "narration.mp3"


def build_text():
    data = json.loads(BRIEFS.read_text())
    briefs = data.get("briefs", [])
    parts = [f"Here is your trending brief for {data.get('date_label', 'today')}."]
    for i, b in enumerate(briefs, 1):
        # title followed by its description so each item is understandable
        line = f"Number {i}. {b['title']}."
        summary = (b.get("summary") or "").strip()
        if summary:
            line += f" {summary}"
        parts.append(line)
    parts.append("That's all the trending stories for now.")
    return "  ".join(parts)


async def synth(text):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE, rate="+0%")
    await communicate.save(str(OUT))


def main():
    try:
        text = build_text()
        asyncio.run(synth(text))
        print(f"Wrote {OUT} ({OUT.stat().st_size} bytes) with voice {VOICE}")
    except Exception as e:
        # Non-fatal: the site falls back to the browser voice if there's no MP3.
        print(f"Narration generation skipped: {e}", file=sys.stderr)
        # remove any stale/partial file so the site doesn't play garbage
        try:
            OUT.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
