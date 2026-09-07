(() => {
  "use strict";

  const DAYS_DIR = "days";
  const INDEX_URL = `${DAYS_DIR}/index.json`;

  const els = {
    main: document.getElementById("main"),
    nav: document.getElementById("story-nav"),
    prevBtn: document.getElementById("prev-btn"),
    nextBtn: document.getElementById("next-btn"),
    jumpSelect: document.getElementById("jump-select"),
    todayBtn: document.getElementById("today-btn"),
    shareBtn: document.getElementById("share-btn"),
    shareTooltip: document.getElementById("share-tooltip"),
    dayCounter: document.getElementById("day-counter"),
    homeLink: document.getElementById("home-link"),
  };

  /** @type {{day:number, date:string, title:string}[]} sorted ascending by day */
  let index = [];
  let currentPos = -1; // position within `index`
  const entryCache = new Map(); // day number -> full entry payload

  // ---------- rendering: states ----------

  function renderLoading() {
    els.main.innerHTML = `<div class="state state-loading"><p>Finding today's page&hellip;</p></div>`;
  }

  function renderEmpty() {
    els.main.innerHTML = `
      <div class="state state-empty">
        <p>James hasn't started his journey yet. Check back soon for the first page.</p>
      </div>`;
    els.nav.hidden = true;
    els.dayCounter.textContent = "";
  }

  function renderError(message, onRetry) {
    els.main.innerHTML = `
      <div class="state state-error">
        <p>${message}</p>
        <button class="retry-btn" type="button">Try again</button>
      </div>`;
    els.main.querySelector(".retry-btn").addEventListener("click", onRetry);
  }

  function paragraphsFromStory(story) {
    // Handle both literal \n\n (which might come from JSON as \\n\\n) 
    // and actual newline characters.
    return story
      .replace(/\\n/g, "\n")
      .split(/\n{2,}/)
      .map((p) => p.trim())
      .filter(Boolean)
      .map((p) => `<p>${escapeHtml(p)}</p>`)
      .join("");
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function formatDate(isoDate) {
    const d = new Date(`${isoDate}T00:00:00`);
    return d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  }

  function renderEntry(entry, direction) {
    const wrap = document.createElement("div");
    wrap.className = "entry" + (direction === "older" ? " dir-older" : "");
    wrap.innerHTML = `
      <p class="entry-date">${formatDate(entry.date)}</p>
      <h1 class="entry-title">${escapeHtml(entry.title)}</h1>
      <div class="entry-image-wrap">
        <img src="${DAYS_DIR}/${encodeURIComponent(entry.image)}" alt="${escapeHtml(entry.title)}" />
      </div>
      <div class="entry-story">${paragraphsFromStory(entry.story)}</div>
      <p class="entry-location">${escapeHtml(entry.location)}</p>
    `;
    els.main.replaceChildren(wrap);
    attachSwipe(wrap);
  }

  // ---------- data loading ----------

  async function fetchJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  async function loadIndex() {
    // Cache-bust: GitHub Pages sets Cache-Control: max-age=600 on everything it
    // serves and gives no way to override it, so a plain fetch -- even with
    // {cache:"no-store"} -- can still get a stale copy back from GitHub's own
    // CDN edge cache. A changing query string makes it a "new" URL as far as
    // that CDN cache is concerned, forcing a real fetch of the current file.
    const raw = await fetchJson(`${INDEX_URL}?_=${Date.now()}`);
    index = [...raw].sort((a, b) => a.day - b.day);
  }

  async function loadEntry(dayNumber) {
    if (entryCache.has(dayNumber)) return entryCache.get(dayNumber);
    const entry = await fetchJson(`${DAYS_DIR}/day${dayNumber}.json`);
    entryCache.set(dayNumber, entry);
    return entry;
  }

  // ---------- navigation ----------

  function populateJumpSelect() {
    els.jumpSelect.innerHTML = index
      .map((e) => `<option value="${e.day}">Day ${e.day} — ${formatDate(e.date)}</option>`)
      .reverse()
      .join("");
  }

  function updateNavState() {
    els.prevBtn.disabled = currentPos <= 0;
    els.nextBtn.disabled = currentPos >= index.length - 1;
    els.jumpSelect.value = String(index[currentPos].day);
    els.todayBtn.hidden = currentPos === index.length - 1;
    els.dayCounter.textContent = `Day ${index[currentPos].day} of ${index.length}`;
  }

  async function goTo(pos, direction) {
    if (pos < 0 || pos >= index.length) return;
    currentPos = pos;
    const dayNumber = index[currentPos].day;
    if (location.hash) {
      history.replaceState(null, "", location.pathname + location.search);
    }
    updateNavState();
    try {
      const entry = await loadEntry(dayNumber);
      renderEntry(entry, direction);
    } catch (err) {
      renderError("Couldn't load that entry — check your connection.", () => goTo(pos, direction));
    }
  }

  function goPrev() {
    goTo(currentPos - 1, "older");
  }

  function goNext() {
    goTo(currentPos + 1, "newer");
  }

  function goToday() {
    goTo(index.length - 1, "newer");
  }

  // Re-checks for new content when the tab comes back to life -- whether
  // that's a genuine reload, or the browser silently resuming a page it had
  // frozen/discarded in the background (which does NOT re-run init(), so
  // without this a long-lived tab can be stuck showing whatever was newest
  // the moment it was first opened, forever).
  async function refreshIfStale() {
    const wasAtLatest = currentPos === index.length - 1;
    const previousNewestDay = index.length ? index[index.length - 1].day : null;
    try {
      await loadIndex();
    } catch (err) {
      return; // transient network hiccup -- leave whatever's already on screen alone
    }
    populateJumpSelect();
    const newestDay = index.length ? index[index.length - 1].day : null;
    if (wasAtLatest && newestDay !== null && newestDay !== previousNewestDay) {
      // They were already looking at "today" -- follow it forward to the new today.
      goTo(index.length - 1, "newer");
      return;
    }
    // Otherwise leave them exactly where they were (don't yank someone out of
    // an old entry they're reading), just re-sync the position pointer and
    // nav bar in case the day count changed underneath them.
    const day = index[currentPos]?.day ?? previousNewestDay;
    const pos = index.findIndex((e) => e.day === day);
    if (pos !== -1) {
      currentPos = pos;
      updateNavState();
    }
  }

  function attachRefreshOnReturn() {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refreshIfStale();
    });
    window.addEventListener("pageshow", (e) => {
      if (e.persisted) refreshIfStale();
    });
  }

  // ---------- input handling ----------

  function attachSwipe(target) {
    let startX = null;
    let startY = null;

    target.addEventListener(
      "touchstart",
      (e) => {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      },
      { passive: true }
    );

    target.addEventListener(
      "touchend",
      (e) => {
        if (startX === null) return;
        const dx = e.changedTouches[0].clientX - startX;
        const dy = e.changedTouches[0].clientY - startY;
        startX = null;
        if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy)) return; // not a horizontal swipe
        if (dx < 0) goNext();
        else goPrev();
      },
      { passive: true }
    );
  }

  function attachKeyboard() {
    window.addEventListener("keydown", (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    });
  }

  function attachControls() {
    els.prevBtn.addEventListener("click", goPrev);
    els.nextBtn.addEventListener("click", goNext);
    els.todayBtn.addEventListener("click", goToday);
    els.shareBtn.addEventListener("click", () => {
      const dayNumber = index[currentPos].day;
      const url = new URL(location.href);
      url.hash = `day-${dayNumber}`;
      navigator.clipboard?.writeText(url.toString()).catch(() => {});
      
      if (els.shareTooltip) {
        els.shareTooltip.style.opacity = "1";
        setTimeout(() => {
          els.shareTooltip.style.opacity = "0";
        }, 2000);
      }
    });
    els.jumpSelect.addEventListener("change", () => {
      const day = Number(els.jumpSelect.value);
      const pos = index.findIndex((e) => e.day === day);
      const direction = pos > currentPos ? "newer" : "older";
      goTo(pos, direction);
    });
    els.homeLink.addEventListener("click", (e) => {
      e.preventDefault();
      goToday();
    });
    window.addEventListener("hashchange", () => {
      const match = location.hash.match(/^#day-(\d+)$/);
      if (!match) return;
      const day = Number(match[1]);
      const pos = index.findIndex((e) => e.day === day);
      if (pos !== -1 && pos !== currentPos) {
        const direction = pos > currentPos ? "newer" : "older";
        goTo(pos, direction);
      }
    });
  }

  // ---------- boot ----------

  async function init() {
    renderLoading();
    try {
      await loadIndex();
    } catch (err) {
      renderError("Couldn't load the archive — check your connection.", init);
      return;
    }

    if (index.length === 0) {
      renderEmpty();
      return;
    }

    populateJumpSelect();
    els.nav.hidden = false;
    attachControls();
    attachKeyboard();
    attachRefreshOnReturn();

    const match = location.hash.match(/^#day-(\d+)$/);
    const newestDay = index[index.length - 1].day;
    let requestedDay = match ? Number(match[1]) : null;

    // Check if the requested day exists in our index. If not, or if it is older than the newest, we might want to consider keeping it, 
    // but the original intent seemed to be forcing the newest.
    // If the user has a link to an older day, it should probably show that older day.
    // The previous code explicitly forced newest if it wasn't newest.
    // Let's ensure the requested day exists before accepting it.

    const startPos = requestedDay !== null ? index.findIndex((e) => e.day === requestedDay) : -1;

    await goTo(startPos !== -1 ? startPos : index.length - 1, "newer");
  }

  init();
})();
