/* On It — trending brief front-end. No frameworks, no build step. */

(() => {
  "use strict";

  const SAVE_KEY = "onit.saved.v1";
  const THEME_KEY = "onit.theme";
  const SAVE_TTL_DAYS = 7;

  const el = {
    dateLabel: document.getElementById("date-label"),
    feed: document.getElementById("feed"),
    filters: document.getElementById("filters"),
    banner: document.getElementById("banner"),
    empty: document.getElementById("empty"),
    themeToggle: document.getElementById("theme-toggle"),
    narrateBtn: document.getElementById("narrate-btn"),
    narrateLabel: document.getElementById("narrate-label"),
    stopBtn: document.getElementById("stop-btn"),
    nowReading: document.getElementById("now-reading"),
    audio: document.getElementById("narration-audio"),
  };

  const state = { data: null, briefs: [], view: "all", hasAudio: false };

  // ---------------------------------------------------------------- theme
  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    el.themeToggle.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme");
      const prefersDark = matchMedia("(prefers-color-scheme: dark)").matches;
      const next = cur ? (cur === "dark" ? "light" : "dark") : (prefersDark ? "light" : "dark");
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem(THEME_KEY, next);
    });
  }

  // ---------------------------------------------------------------- saved
  function loadSaved() {
    let map = {};
    try { map = JSON.parse(localStorage.getItem(SAVE_KEY)) || {}; } catch (_) {}
    const cutoff = Date.now() - SAVE_TTL_DAYS * 86400000;
    let changed = false;
    for (const id of Object.keys(map)) {
      if (!map[id] || map[id].savedAt < cutoff) { delete map[id]; changed = true; }
    }
    if (changed) localStorage.setItem(SAVE_KEY, JSON.stringify(map));
    return map;
  }
  function isSaved(id) { return !!loadSaved()[id]; }
  function toggleSave(brief) {
    const map = loadSaved();
    if (map[brief.id]) delete map[brief.id];
    else map[brief.id] = { savedAt: Date.now(), brief };
    localStorage.setItem(SAVE_KEY, JSON.stringify(map));
  }
  function savedBriefs() {
    return Object.values(loadSaved()).sort((a, b) => b.savedAt - a.savedAt).map((x) => x.brief);
  }

  // ---------------------------------------------------------------- render
  function currentList() {
    return state.view === "saved" ? savedBriefs() : state.briefs;
  }

  function render() {
    const list = currentList();
    el.feed.innerHTML = "";
    if (!list.length) {
      el.empty.hidden = false;
      el.empty.textContent = state.view === "saved"
        ? "No saved briefs yet. Tap 📌 Save on anything you want to keep — pins last 7 days."
        : "Nothing trending right now. Check back after the next refresh.";
      return;
    }
    el.empty.hidden = true;
    list.forEach((b, i) => el.feed.appendChild(card(b, i)));
  }

  function card(b, i) {
    const node = document.createElement("article");
    node.className = "card";
    node.dataset.id = b.id;
    const saved = isSaved(b.id);
    const meta = [b.trend ? `🔎 ${b.trend}` : "", b.engagement, b.source]
      .filter(Boolean).map((s) => `<span class="src">${escapeHtml(s)}</span>`)
      .join('<span class="dot">·</span>');

    node.innerHTML = `
      <div class="card-top">
        <span class="rank">#${i + 1}</span>
        ${b.badge ? `<span class="cat-tag">🔥 ${escapeHtml(b.badge)}</span>` : ""}
      </div>
      <h2>${escapeHtml(b.title)}</h2>
      <p class="summary">${escapeHtml(b.summary || "")}</p>
      <div class="card-meta">${meta}</div>
      <div class="card-actions">
        <a class="btn btn-learn" href="${encodeURI(b.url || "#")}" target="_blank" rel="noopener">Learn more ↗</a>
        <button class="btn btn-save ${saved ? "saved" : ""}">${saved ? "📌 Saved" : "📌 Save"}</button>
      </div>`;
    node.querySelector(".btn-save").addEventListener("click", () => { toggleSave(b); render(); });
    return node;
  }

  function initFilters() {
    el.filters.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      state.view = chip.dataset.view;
      el.filters.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      render();
    });
  }

  // ------------------------------------------------------------ narration
  // Preferred path: play the pre-generated neural-voice MP3 (titles only).
  // Fallback: browser speech synthesis reading titles only.
  let speaking = false;

  function titlesText() {
    const list = currentList();
    const parts = [`Here is your trending brief for ${state.data.date_label}.`];
    list.forEach((b, i) => parts.push(`Number ${i + 1}. ${b.title}.`));
    parts.push("That's all the trending stories for now.");
    return parts.join("  ");
  }

  function startNarration() {
    if (state.hasAudio && state.view === "all") {
      el.audio.currentTime = 0;
      el.audio.play().then(showPlaying).catch(fallbackSpeak);
    } else {
      fallbackSpeak();
    }
  }

  function fallbackSpeak() {
    if (!("speechSynthesis" in window)) {
      alert("Voice narration isn't supported in this browser.");
      return;
    }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(titlesText());
    // best available English voice, preferring Indian English
    const voices = speechSynthesis.getVoices();
    const pick = voices.find((v) => (v.lang || "").toLowerCase() === "en-in")
      || voices.find((v) => /natural|google/i.test(v.name) && /^en/i.test(v.lang))
      || voices.find((v) => /^en/i.test(v.lang));
    if (pick) { u.voice = pick; u.lang = pick.lang; } else { u.lang = "en-IN"; }
    u.rate = 0.98;
    u.onend = endNarration;
    u.onerror = endNarration;
    speaking = true;
    showPlaying();
    speechSynthesis.speak(u);
  }

  function showPlaying() {
    el.narrateBtn.disabled = true;
    el.narrateLabel.textContent = "Narrating…";
    el.stopBtn.hidden = false;
    el.nowReading.hidden = false;
    el.nowReading.textContent = "▶ Reading today's headlines…";
  }

  function endNarration() {
    speaking = false;
    try { el.audio.pause(); } catch (_) {}
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    el.narrateBtn.disabled = false;
    el.narrateLabel.textContent = "Narrate the headlines";
    el.stopBtn.hidden = true;
    el.nowReading.hidden = true;
  }

  function initNarration() {
    el.narrateBtn.addEventListener("click", startNarration);
    el.stopBtn.addEventListener("click", endNarration);
    el.audio.addEventListener("ended", endNarration);
  }

  // ------------------------------------------------------------ utils
  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function showBanner(msg) { el.banner.hidden = false; el.banner.textContent = msg; }

  // ------------------------------------------------------------ boot
  async function boot() {
    initTheme();
    try {
      const res = await fetch("data/briefs.json?_=" + Date.now());
      if (!res.ok) throw new Error("no data");
      state.data = await res.json();
    } catch (e) {
      el.dateLabel.textContent = "Couldn't load the brief.";
      showBanner("No brief data yet. Run the daily crawler (GitHub Action) to populate it.");
      return;
    }
    state.briefs = state.data.briefs || [];
    el.dateLabel.textContent = `${state.data.date_label} · ${state.briefs.length} trending`;
    if (state.data.sample) {
      showBanner("👋 Showing sample data. Your first daily GitHub Action run will replace these with real trending searches.");
    }

    // wire up the neural-voice MP3 if it exists
    const audioUrl = "data/narration.mp3?v=" + encodeURIComponent(state.data.generated_at || "");
    try {
      const head = await fetch(audioUrl, { method: "HEAD" });
      if (head.ok) { state.hasAudio = true; el.audio.src = audioUrl; }
    } catch (_) { /* fall back to browser voice */ }

    initFilters();
    initNarration();
    render();
  }

  boot();
})();
