# On It 📰

Your personal daily brief. Every morning it shows the **trending** things across
**AI · Design · Marketing · Tech**, and a voice can read the whole brief out loud
in an **Indian‑English accent**.

Everything runs for free on GitHub — no servers, no API keys, no paid services.

---

## How it works

```
GitHub Action (daily cron)          Your browser
─────────────────────────           ─────────────────────
scripts/fetch_briefs.py     ──▶      index.html
  ├─ Hacker News API                   reads data/briefs.json
  ├─ Reddit top‑of‑day                 renders the cards
  └─ Google News RSS                   🔊 narrates via Web Speech API
        │                              📌 saves pins (7 days) in your browser
        ▼
   data/briefs.json  ──(committed & deployed to GitHub Pages)──▶ the live site
```

- **Trending, not just new.** Items are ranked by real engagement — Hacker News
  points, Reddit upvotes, and fresh news coverage — then balanced across your
  four interests and trimmed to the top ~20.
- **A fresh brief every morning.** A scheduled GitHub Action runs at **00:30 UTC
  (06:00 IST)**, regenerates `data/briefs.json`, commits it, and redeploys.
- **Voice narration.** The **Narrate** button uses your browser's built‑in
  speech engine and automatically prefers an `en-IN` (Indian‑English) voice. You
  can pick a different voice from the dropdown. No cloud, no cost.
- **Save for later.** Tap **📌 Save** on any brief to pin it. Pins live in your
  browser's `localStorage` and auto‑expire after **7 days**. Un‑saved briefs
  simply roll off when the next day's brief replaces the file.

> Twitter/X was in the original idea, but its API is now paid. Hacker News,
> Reddit and Google News are the free, no‑auth equivalents that give the same
> "what's trending today" signal — swap or add sources in `scripts/fetch_briefs.py`.

---

## One‑time setup

1. **Merge this branch to `main`.**
2. In the repo, go to **Settings → Pages**.
3. Under **Build and deployment → Source**, choose **GitHub Actions**.
4. Go to the **Actions** tab, open **Daily brief**, and click **Run workflow**
   once to populate real data immediately (otherwise it waits for the next
   morning's schedule).

Your site will be live at:

```
https://abiknewar.github.io/on-it/
```

That's it. From then on it refreshes itself every morning.

---

## Customising your interests

Open `scripts/fetch_briefs.py` and edit the `INTERESTS` dictionary — add a niche,
change the subreddits, tweak the Hacker News / news search queries. The site
picks up new categories automatically from the generated JSON.

```python
INTERESTS = {
    "AI":        { "emoji": "🤖", "hn_query": "...", "subreddits": [...], "news_query": "..." },
    "Design":    { ... },
    "Marketing": { ... },
    "Tech":      { ... },
    # add your own here
}
```

You can also change how many briefs to keep (`TARGET_TOTAL`) and the per‑interest
cap (`MAX_PER_CATEGORY`).

---

## Run it locally

```bash
# regenerate the brief (needs plain internet access to the sources)
python3 scripts/fetch_briefs.py

# serve the static site
python3 -m http.server 8000
# then open http://localhost:8000
```

No dependencies to install — the crawler uses only the Python standard library.

---

## Files

| Path | What it is |
|------|------------|
| `index.html` | The app shell |
| `assets/style.css` | Styling (light/dark, responsive) |
| `assets/app.js` | Rendering, narration, saving, filtering |
| `data/briefs.json` | The generated brief (starts as sample data) |
| `scripts/fetch_briefs.py` | The daily crawler / ranker |
| `.github/workflows/daily-brief.yml` | Cron + build + Pages deploy |
