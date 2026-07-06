/* On It — daily brief front-end. No frameworks, no build step. */

(() => {
  "use strict";

  const SAVE_KEY = "onit.saved.v1";
  const THEME_KEY = "onit.theme";
  const VOICE_KEY = "onit.voice";
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
    pauseBtn: document.getElementById("pause-btn"),
    stopBtn: document.getElementById("stop-btn"),
    voiceSelect: document.getElementById("voice-select"),
    nowReading: document.getElementById("now-reading"),
  };

  let state = {
    data: null,
    briefs: [],
    filter: "all",
  };

  // ---------------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------------
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

  // ---------------------------------------------------------------------
  // Saved pins (localStorage, auto-pruned after 7 days)
  // ---------------------------------------------------------------------
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
    if (map[brief.id]) {
      delete map[brief.id];
    } else {
      map[brief.id] = { savedAt: Date.now(), brief };
    }
    localStorage.setItem(SAVE_KEY, JSON.stringify(map));
  }

  function savedBriefs() {
    const map = loadSaved();
    return Object.values(map)
      .sort((a, b) => b.savedAt - a.savedAt)
      .map((x) => x.brief);
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------
  function catEmoji(name) {
    const found = (state.data?.interests || []).find((i) => i.name === name);
    return found ? found.emoji : "•";
  }

  function briefsForFilter() {
    if (state.filter === "__saved__") return savedBriefs();
    if (state.filter === "all") return state.briefs;
    return state.briefs.filter((b) => b.category === state.filter);
  }

  function render() {
    const list = briefsForFilter();
    el.feed.innerHTML = "";

    if (!list.length) {
      el.empty.hidden = false;
      el.empty.textContent = state.filter === "__saved__"
        ? "No saved briefs yet. Tap 📌 Save on anything you want to keep — pins last 7 days."
        : "No briefs here right now. Check back after the next daily refresh.";
      return;
    }
    el.empty.hidden = true;

    for (const b of list) {
      el.feed.appendChild(card(b));
    }
  }

  function card(b) {
    const node = document.createElement("article");
    node.className = "card";
    node.dataset.id = b.id;

    const saved = isSaved(b.id);
    const meta = [b.source, b.engagement].filter(Boolean)
      .map((s) => `<span class="src">${escapeHtml(s)}</span>`)
      .join('<span class="dot">·</span>');

    node.innerHTML = `
      <div class="card-top">
        <span class="cat-tag">${catEmoji(b.category)} ${escapeHtml(b.category)}</span>
      </div>
      <h2>${escapeHtml(b.title)}</h2>
      <p class="summary">${escapeHtml(b.summary || "")}</p>
      <div class="card-meta">${meta}</div>
      <div class="card-actions">
        <a class="btn btn-learn" href="${encodeURI(b.url || "#")}" target="_blank" rel="noopener">Learn more ↗</a>
        <button class="btn btn-save ${saved ? "saved" : ""}">${saved ? "📌 Saved" : "📌 Save"}</button>
      </div>
    `;

    node.querySelector(".btn-save").addEventListener("click", () => {
      toggleSave(b);
      render();
    });
    return node;
  }

  function renderFilters() {
    // insert interest chips between "All" and "Saved"
    const savedChip = el.filters.querySelector(".chip-saved");
    for (const i of state.data.interests) {
      const c = document.createElement("button");
      c.className = "chip";
      c.dataset.cat = i.name;
      c.textContent = `${i.emoji} ${i.name}`;
      el.filters.insertBefore(c, savedChip);
    }
    el.filters.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      state.filter = chip.dataset.cat;
      el.filters.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      render();
    });
  }

  // ---------------------------------------------------------------------
  // Narration (Web Speech API) — prefers an Indian-English voice
  // ---------------------------------------------------------------------
  let voices = [];
  let queue = [];
  let speaking = false;

  function loadVoices() {
    voices = speechSynthesis.getVoices();
    el.voiceSelect.innerHTML = "";

    // rank: en-IN first, then anything with "India"/"Hindi", then other English
    const ranked = [...voices].sort((a, b) => score(b) - score(a));
    function score(v) {
      let s = 0;
      const lang = (v.lang || "").toLowerCase();
      const name = (v.name || "").toLowerCase();
      if (lang === "en-in") s += 100;
      if (/india|hindi/.test(name)) s += 60;
      if (lang.startsWith("en")) s += 20;
      return s;
    }

    ranked.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = `${v.name} (${v.lang})`;
      el.voiceSelect.appendChild(opt);
    });

    const savedVoice = localStorage.getItem(VOICE_KEY);
    if (savedVoice && ranked.some((v) => v.name === savedVoice)) {
      el.voiceSelect.value = savedVoice;
    } else if (ranked.length) {
      el.voiceSelect.value = ranked[0].name; // best Indian-English match
    }
  }

  function chosenVoice() {
    return voices.find((v) => v.name === el.voiceSelect.value) || null;
  }

  function buildScript() {
    const list = briefsForFilter();
    const d = state.data;
    const parts = [];
    const scope = state.filter === "all" ? "today's" :
                  state.filter === "__saved__" ? "your saved" :
                  `today's ${state.filter}`;
    parts.push({
      text: `Here is ${scope} brief for ${d.date_label}. There are ${list.length} ${list.length === 1 ? "story" : "stories"} to catch you up.`,
      id: null,
    });
    list.forEach((b, i) => {
      parts.push({
        text: `Story ${i + 1}, in ${b.category}. ${b.title}. ${b.summary || ""} Source: ${cleanSource(b.source)}.`,
        id: b.id,
      });
    });
    parts.push({ text: "That's your brief. You're all caught up.", id: null });
    return parts;
  }

  function cleanSource(s) {
    return (s || "").replace(/·/g, " from ");
  }

  function speakNext() {
    if (!queue.length) { endNarration(); return; }
    const part = queue.shift();
    highlight(part.id);

    const u = new SpeechSynthesisUtterance(part.text);
    const v = chosenVoice();
    if (v) { u.voice = v; u.lang = v.lang; }
    else { u.lang = "en-IN"; }
    u.rate = 0.98;
    u.pitch = 1.0;
    u.onend = speakNext;
    u.onerror = speakNext;
    speechSynthesis.speak(u);
  }

  function highlight(id) {
    document.querySelectorAll(".card.reading").forEach((c) => c.classList.remove("reading"));
    if (!id) { el.nowReading.hidden = true; return; }
    const card = el.feed.querySelector(`.card[data-id="${id}"]`);
    if (card) {
      card.classList.add("reading");
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      const title = card.querySelector("h2")?.textContent || "";
      el.nowReading.hidden = false;
      el.nowReading.textContent = "▶ " + title;
    }
  }

  function startNarration() {
    if (!("speechSynthesis" in window)) {
      alert("Your browser doesn't support voice narration.");
      return;
    }
    speechSynthesis.cancel();
    queue = buildScript();
    speaking = true;
    el.narrateLabel.textContent = "Narrating…";
    el.narrateBtn.disabled = true;
    el.pauseBtn.hidden = false;
    el.stopBtn.hidden = false;
    speakNext();
  }

  function endNarration() {
    speaking = false;
    speechSynthesis.cancel();
    el.narrateBtn.disabled = false;
    el.narrateLabel.textContent = "Narrate today's brief";
    el.pauseBtn.hidden = true;
    el.stopBtn.hidden = true;
    el.pauseBtn.textContent = "⏸ Pause";
    el.nowReading.hidden = true;
    document.querySelectorAll(".card.reading").forEach((c) => c.classList.remove("reading"));
  }

  function initNarration() {
    loadVoices();
    // voices load async in most browsers
    if (speechSynthesis.onvoiceschanged !== undefined) {
      speechSynthesis.onvoiceschanged = loadVoices;
    }
    el.voiceSelect.addEventListener("change", () =>
      localStorage.setItem(VOICE_KEY, el.voiceSelect.value));

    el.narrateBtn.addEventListener("click", startNarration);
    el.stopBtn.addEventListener("click", endNarration);
    el.pauseBtn.addEventListener("click", () => {
      if (speechSynthesis.paused) {
        speechSynthesis.resume();
        el.pauseBtn.textContent = "⏸ Pause";
      } else {
        speechSynthesis.pause();
        el.pauseBtn.textContent = "▶ Resume";
      }
    });
  }

  // ---------------------------------------------------------------------
  // Utils
  // ---------------------------------------------------------------------
  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function showBanner(msg) {
    el.banner.hidden = false;
    el.banner.textContent = msg;
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------
  async function boot() {
    initTheme();
    try {
      const res = await fetch("data/briefs.json?_=" + Date.now());
      if (!res.ok) throw new Error("no data file");
      state.data = await res.json();
    } catch (e) {
      el.dateLabel.textContent = "Couldn't load today's brief.";
      showBanner("No brief data found yet. Run the daily crawler (GitHub Action) to populate it.");
      return;
    }

    state.briefs = state.data.briefs || [];
    el.dateLabel.textContent = `${state.data.date_label} · ${state.briefs.length} briefs`;

    if (state.data.sample) {
      showBanner("👋 Showing sample briefs. Your first daily GitHub Action run will replace these with real trending stories.");
    }

    renderFilters();
    initNarration();
    render();
  }

  boot();
})();
