// My Money — browser side.
// This file has no finance logic: it asks the Python server for a page (/api/page/<name>) and draws
// the blocks it gets back (see web/blocks.py for the list). To change what a page shows, edit Python.

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };
// fetch, except that a signed-out (or expired) session goes back to the sign-in page
async function api(url, options) {
  const r = await fetch(url, options);
  if (r.status === 401) {   // signed out: forget the copies kept in this browser too
    try { localStorage.removeItem("gastos.entries"); await Promise.all((await caches.keys()).map((k) => caches.delete(k))); } catch {}
    location.href = "/login?next=/portfolio";
    throw new Error("Signing in…");
  }
  return r;
}

// ---------- Routing: #/page?param=value ----------
function route() {
  const [path, query] = location.hash.replace(/^#\/?/, "").split("?");
  return { page: path || "overview", params: new URLSearchParams(query || "") };
}
function go(page, params) {
  const q = params.toString();
  location.hash = `#/${page}${q ? "?" + q : ""}`;
}

let loadToken = 0;
async function load() {
  const { page, params } = route();
  // a tab that is hidden (demo data, Backtest switched off) can still be in the address from before: go to Overview
  if ($(`#tabs a[data-page="${page}"]`)?.hidden) return go("overview", new URLSearchParams());
  document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
  const tab = $("#tabs a.active"), tabs = $("#tabs");
  if (tab) tabs.scrollTo({ left: tab.offsetLeft - (tabs.clientWidth - tab.offsetWidth) / 2, behavior: "smooth" });
  const token = ++loadToken;
  showSkeleton();
  let res, offline = false;
  try {
    ({ res, offline } = await fetchPage(`/api/page/${page}?${params}`));
  } catch (e) {
    res = { error: `Could not reach the server (${e.message}). Is app.py running?` };
  }
  if (token !== loadToken) return; // the user already moved on to another page
  setOffline(offline);
  render(page, params, res);
}

// Every page that loads is kept in the browser; with no connection the last copy is shown instead.
const PAGE_CACHE = "portfolio-pages";
async function fetchPage(url) {
  try {
    const r = await api(url);
    const res = await r.json();
    if (r.ok && window.caches) caches.open(PAGE_CACHE).then((c) => c.put(url, new Response(JSON.stringify(res)))).catch(() => {});
    return { res, offline: false };
  } catch (e) {
    if (e.message === "Signing in…") throw e;
    const saved = window.caches && await caches.open(PAGE_CACHE).then((c) => c.match(url)).catch(() => null);
    if (!saved) throw new Error("offline, and this view hasn't been opened before");
    return { res: await saved.json(), offline: true };
  }
}

// Offline you can look but not add: a snapshot needs the server.
function setOffline(offline) {
  const b = $("#banner");
  b.hidden = !offline;
  b.textContent = offline ? "Offline — showing the last data seen. Snapshots can't be added until you're back online." : "";
  $("#new-snapshot").disabled = offline;
}

function showSkeleton() {
  $("#hero").className = "hero loading";
  $("#hero").innerHTML = `<div class="label">Loading…</div><div class="value"></div>`;
  $("#sections").innerHTML = `<div class="card half skeleton"></div><div class="card half skeleton"></div><div class="card skeleton"></div>`;
}

// ---------- Page ----------
function render(page, params, res) {
  if (res.error) {
    $("#hero").className = "hero";
    $("#hero").innerHTML = `<div class="label">Something went wrong</div><div class="caption">${esc(res.error)}</div>`;
    $("#controls").innerHTML = "";
    $("#sections").innerHTML = "";
    return;
  }
  renderHero(res.hero);
  renderControls(page, params, res.controls || []);
  const grid = $("#sections");
  grid.innerHTML = "";
  for (const s of res.sections || []) if (s) grid.appendChild(renderSection(s));
}

function renderHero(h) {
  const el = $("#hero");
  el.className = "hero";
  if (!h) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `
    <div class="label">${esc(h.label)}</div>
    <div class="value">${esc(h.value)}${h.unit ? `<small>${esc(h.unit)}</small>` : ""}</div>
    ${h.caption ? `<div class="caption">${esc(h.caption)}</div>` : ""}
    <div class="chips">${h.chips.map((c) => `<span class="chip ${c.tone || ""}">${esc(c.text)}</span>`).join("")}</div>`;
}

function renderControls(page, params, controls) {
  const box = $("#controls");
  box.innerHTML = "";
  for (const c of controls) {
    if (c.type === "chips") {
      const row = document.createElement("div");
      row.className = "choice";
      row.innerHTML = c.options.map((o) => `<button type="button" data-v="${esc(o.value)}" class="${o.value === c.value ? "on" : ""}">${esc(o.label)}</button>`).join("");
      row.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (!b) return;
        const p = new URLSearchParams(params);
        p.set(c.name, b.dataset.v);
        go(page, p);
      });
      box.appendChild(row);
      continue;
    }
    const label = document.createElement("label");
    label.className = c.type === "toggle" ? "field switch" : "field";
    let input;
    if (c.type === "select") {
      input = document.createElement("select");
      input.innerHTML = c.options.map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("");
      input.value = c.value;
    } else if (c.type === "toggle") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = c.value;
    } else {
      input = document.createElement("input");
      input.type = c.type; // "number" or "date"
      input.value = c.value;
      if (c.min != null) input.min = c.min;
      if (c.max != null) input.max = c.max;
      if (c.step != null) input.step = c.step;
    }
    input.addEventListener("change", () => {
      const p = new URLSearchParams(params);
      p.set(c.name, c.type === "toggle" ? (input.checked ? "1" : "0") : input.value);
      go(page, p);
    });
    label.innerHTML = `<span>${esc(c.label)}</span>`;
    label.appendChild(input);
    if (c.type === "toggle") label.appendChild(document.createElement("i"));
    box.appendChild(label);
  }
}

function renderSection(s) {
  const card = document.createElement("section");
  card.className = `card ${s.width === "half" ? "half" : ""} ${s.error ? "error" : ""} ${s.bare ? "bare" : ""}`;
  card.id = s.id;
  card.innerHTML = `${s.bare ? "" : `<h2>${esc(s.title)}</h2>`}${s.subtitle && !s.bare ? `<p class="sub">${esc(s.subtitle)}</p>` : ""}<div class="body"></div>`;
  const body = $(".body", card);
  if (s.error) { body.textContent = s.error; return card; }
  for (const b of s.blocks || []) {
    const draw = BLOCKS[b.type];
    if (draw) draw(body, b);
  }
  return card;
}

// ---------- Look (settings.py > Look) ----------
const CHART_SCALE = { compact: 0.85, normal: 1, tall: 1.2 };
let look = {};
function applyLook(values) {
  look = values || {};
  const d = document.documentElement.dataset;
  d.privacy = look.privacy ? "on" : "off";
  d.motion = look.motion === false ? "off" : "on";
}

// Small buttons in the corner of every chart: fill the screen, save as a picture
function addChartTools(el) {
  const card = el.closest(".card");
  if (!card || $(".tools", card)) return;
  const tools = document.createElement("div");
  tools.className = "tools";
  tools.innerHTML = `<button type="button" data-t="full" title="Fill the screen (Esc to close)" aria-label="Expand">⤢</button>
    <button type="button" data-t="png" title="Save as a picture" aria-label="Save as PNG">⤓</button>`;
  tools.addEventListener("click", (e) => {
    const t = e.target.closest("button")?.dataset.t;
    const plot = $(".chart .js-plotly-plot, .chart", card);
    if (t === "full") {
      card.classList.toggle("fullscreen");
      document.body.classList.toggle("has-fullscreen", card.classList.contains("fullscreen"));
      setTimeout(() => { Plotly.relayout(el, { height: card.classList.contains("fullscreen") ? Math.round(innerHeight * 0.72) : null }); Plotly.Plots.resize(el); }, 60);
    } else if (t === "png") {
      Plotly.downloadImage(plot || el, { format: "png", filename: `my-money-${card.id}`, scale: 2 });
    }
  });
  card.appendChild(tools);
}

// ---------- Blocks (one function per type in web/blocks.py) ----------
const BLOCKS = {
  kpis(body, b) {
    const el = document.createElement("div");
    el.className = "kpis";
    el.innerHTML = b.items.map((k) => `
      <div class="kpi">
        <div class="k-label">${esc(k.label)}</div>
        <div class="k-value">${esc(k.value)}</div>
        ${k.sub ? `<div class="k-sub ${k.tone || ""}">${esc(k.sub)}</div>` : ""}
      </div>`).join("");
    body.appendChild(el);
  },

  chart(body, b) {
    const el = document.createElement("div");
    el.className = "chart";
    const fig = b.figure;
    body.appendChild(el);
    const k = CHART_SCALE[look.chart_size] || 1;
    if (k !== 1 && fig.layout.height) fig.layout.height = Math.round(fig.layout.height * k);
    if (look.motion === false) fig.layout.transition = { duration: 0 };
    // wait until the card is in the page so Plotly can measure the width
    requestAnimationFrame(() => {
      Plotly.newPlot(el, fig.data, fig.layout, PLOTLY_CONFIG).then(() => {
        addChartTools(el);
        if (fig.frames) Plotly.addFrames(el, fig.frames);
      });
    });
  },

  table(body, b) {
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    const head = `<tr>${b.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>`;
    const rows = b.rows.map((r) => `<tr>${r.map((c) => `<td class="${c.head ? "head" : ""} ${c.tone || ""}">` +
      (c.bar != null ? `<span class="bar" style="width:${c.bar * 0.8}px"></span>` : "") + `${esc(c.v)}</td>`).join("")}</tr>`).join("");
    wrap.innerHTML = `<table><thead>${head}</thead><tbody>${rows}</tbody></table>`;
    body.appendChild(wrap);
  },

  items(body, b) {
    const el = document.createElement("div");
    el.className = "items";
    el.innerHTML = b.rows.map((r) => `
      <div class="item">
        <div class="dot" style="background:${esc(r.color || "#8B959E")}">${esc((r.title || "?").trim()[0].toUpperCase())}</div>
        <div class="main"><div class="title">${esc(r.title)}</div>${r.subtitle ? `<div class="subtitle">${esc(r.subtitle)}</div>` : ""}</div>
        <div class="right"><div class="value">${esc(r.value)}</div>${r.sub_value ? `<div class="sub-value ${r.tone || ""}">${esc(r.sub_value)}</div>` : ""}</div>
      </div>`).join("");
    body.appendChild(el);
  },

  fold(body, b) {
    // closed by default; the content is drawn on the first open (Plotly needs a visible box to measure)
    const el = document.createElement("details");
    el.className = "fold";
    el.innerHTML = `<summary>${esc(b.label)}</summary><div class="fold-body"></div>`;
    let drawn = false;
    el.addEventListener("toggle", () => {
      if (!el.open || drawn) return;
      drawn = true;
      const inner = $(".fold-body", el);
      for (const x of b.blocks || []) BLOCKS[x.type]?.(inner, x);
      for (const c of b.cards || []) inner.appendChild(renderSection(c));
    });
    body.appendChild(el);
  },

  tabs(body, b) {
    // "More details": a closed header that opens into tabs; each tab is drawn on its first visit
    // (Plotly needs a visible box to measure), and the open/tab choice is remembered in this browser.
    const key = "mymoney.details";
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch {}
    const ids = b.tabs.map((t) => t.name);
    const el = document.createElement("section");
    el.className = "dtabs";
    el.innerHTML = `<button class="dtabs-head" type="button" aria-expanded="false">
        <span class="dtabs-title"><b>${esc(b.label)}</b><small>${b.tabs.length} views · ${b.tabs.reduce((n, t) => n + t.cards.length, 0)} charts</small></span>
        <svg class="chev"><use href="#i-chevron"/></svg></button>
      <div class="dtabs-body" hidden>
        <div class="dtabs-bar" role="tablist">${b.tabs.map((t, i) =>
          `<button type="button" role="tab" data-i="${i}"><span>${esc(t.icon)}</span>${esc(t.name)}</button>`).join("")}</div>
        <p class="dtabs-blurb"></p>
        <div class="dtabs-panes">${b.tabs.map(() => `<div class="dtabs-pane grid" hidden></div>`).join("")}</div>
      </div>`;
    const head = $(".dtabs-head", el), panel = $(".dtabs-body", el);
    const btns = [...el.querySelectorAll(".dtabs-bar button")], panes = [...el.querySelectorAll(".dtabs-pane")];
    const drawn = new Set();
    const show = (i) => {
      btns.forEach((x, j) => { x.classList.toggle("on", i === j); x.setAttribute("aria-selected", i === j); });
      panes.forEach((x, j) => { x.hidden = i !== j; });
      $(".dtabs-blurb", el).textContent = b.tabs[i].blurb || "";
      if (!drawn.has(i)) {
        drawn.add(i);
        for (const c of b.tabs[i].cards) panes[i].appendChild(renderSection(c));
      } else {
        panes[i].querySelectorAll(".js-plotly-plot").forEach((g) => Plotly.Plots.resize(g));
      }
      try { localStorage.setItem(key, JSON.stringify({ ...saved, tab: b.tabs[i].name })); } catch {}
    };
    const toggle = (open) => {
      head.setAttribute("aria-expanded", open);
      el.classList.toggle("open", open);
      panel.hidden = !open;
      try { localStorage.setItem(key, JSON.stringify({ ...saved, open })); } catch {}
      if (open && !drawn.size) show(Math.max(0, ids.indexOf(saved.tab ?? b.start)));
    };
    head.addEventListener("click", () => { saved.open = !el.classList.contains("open"); toggle(saved.open); });
    btns.forEach((x, i) => x.addEventListener("click", () => show(i)));
    body.appendChild(el);
    toggle(saved.open ?? b.open);
  },

  tiles(body, b) {
    const el = document.createElement("div");
    el.className = "tiles";
    el.innerHTML = b.rows.map((t) => `
      <div class="tile" style="--lv:${t.level}">
        <div class="t-icon">${esc(t.icon)}</div>
        <div class="t-label">${esc(t.label)}</div>
        <div class="t-value">${esc(t.value)}</div>
        ${t.sub ? `<div class="t-sub ${t.tone || ""}">${esc(t.sub)}</div>` : ""}
      </div>`).join("");
    body.appendChild(el);
  },

  duel(body, b) {
    const el = document.createElement("div");
    el.className = "duel";
    el.innerHTML = b.sides.map((x) => `
      <div class="side" style="--c:${esc(x.color || "var(--line)")}">
        <div class="name">${esc(x.name)}</div>
        <div class="big">${esc(x.value)}</div>
        ${x.sub ? `<div class="sub">${esc(x.sub)}</div>` : ""}
      </div>`).join("") +
      (b.verdict ? `<div class="verdict ${b.tone || ""}">${b.verdict}</div>` : ""); // verdict escaped by Python (_md)
    body.appendChild(el);
  },

  notes(body, b) {
    const el = document.createElement("ul");
    el.className = "notes";
    el.innerHTML = b.html.map((h) => `<li>${h}</li>`).join(""); // already escaped by Python (_md)
    body.appendChild(el);
  },

  text(body, b) {
    const el = document.createElement("p");
    el.className = "text";
    el.innerHTML = b.html; // already escaped by Python (_md)
    body.appendChild(el);
  },

  action(body, b) {
    const el = document.createElement("div");
    el.className = "upload";
    el.innerHTML = `<button class="pill pill-dark" type="button">${esc(b.label)}</button>
      <span class="muted status">${esc(b.status || "")}</span>`;
    const btn = $("button", el);
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Syncing…";
      try {
        const res = await (await api(b.url, { method: "POST" })).json();
        toast(res.error || res.status, !!res.error);
        if (!res.error) load();
      } catch (e) {
        toast(`Could not reach the server (${e.message})`, true);
      } finally {
        btn.disabled = false;
        btn.textContent = b.label;
      }
    });
    body.appendChild(el);
  },

  upload(body, b) {
    const form = document.createElement("form");
    form.className = "upload";
    form.innerHTML = b.fields.map(([name, label]) => `
      <label class="drop" data-name="${esc(name)}"><input type="file" name="${esc(name)}" accept=".csv,text/csv">
        <b>${esc(label)}</b><span>Click or drop the file here</span></label>`).join("") +
      `<button class="pill pill-light" type="submit">Rebuild savings</button>
       ${b.status ? `<span class="muted status" style="flex-basis:100%">${esc(b.status)}</span>` : ""}`;
    form.querySelectorAll(".drop").forEach((drop) => {
      const input = $("input", drop);
      const mark = () => { if (input.files[0]) { drop.classList.add("ok"); $("span", drop).textContent = input.files[0].name; } };
      input.addEventListener("change", mark);
      drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
      drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
      drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); input.files = e.dataTransfer.files; mark(); });
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const r = await api(b.action, { method: "POST", body: new FormData(form) });
      const res = await r.json();
      toast(res.error || res.status, !!res.error);
      if (!res.error) load();
    });
    body.appendChild(form);
  },
};

// ---------- Toast ----------
let toastTimer;
function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast ${bad ? "bad" : ""}`;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3500);
}

// ---------- Snapshot editor ----------
// Edits a {category: {asset: amount}} dict and POSTs it to /api/snapshot (saved by web/data.py).
const sheet = { categories: {}, portfolio: {} };
const fmtEur = (x) => "€" + Math.round(x).toLocaleString("en-US");
// "100 + 50 - 30" -> 120 (the server parses it the same way, see parse_amount in web/data.py)
const amount = (s) => {
  const t = String(s).replace(/\s/g, "").replace(/,/g, ".");
  return /^[+-]?\d+(\.\d+)?([+-]\d+(\.\d+)?)*$/.test(t) ? t.match(/[+-]?\d+(\.\d+)?/g).reduce((a, b) => a + parseFloat(b), 0) : NaN;
};

async function openSheet(fromDate) {
  const r = await api(`/api/snapshot${fromDate ? "?date=" + fromDate.replaceAll("-", "") : ""}`);
  const res = await r.json();
  sheet.categories = res.categories;
  sheet.portfolio = res.portfolio;
  const from = $("#sheet-from");
  from.innerHTML = res.dates.map((d) => `<option value="${d}">${d}</option>`).join("");
  from.value = res.date;
  if (!fromDate) $("#sheet-date").value = new Date().toISOString().slice(0, 10);
  $("#sheet-msg").textContent = "";
  drawSheet();
  $("#sheet-backdrop").hidden = false;
  document.body.style.overflow = "hidden";
}

function closeSheet() {
  $("#sheet-backdrop").hidden = true;
  document.body.style.overflow = "";
}

function readSheet() {
  // turn the inputs back into {category: {asset: amount}}
  const out = {};
  document.querySelectorAll("#sheet-body .cat").forEach((cat) => {
    const assets = {};
    cat.querySelectorAll(".row").forEach((row) => {
      const name = $(".r-name", row).value.trim();
      const value = $(".r-amount", row).value.trim();
      if (name && value) assets[name] = value; // sent as typed; the server checks it
    });
    out[cat.dataset.cat] = assets;
  });
  return out;
}

function updateTotals() {
  let total = 0;
  document.querySelectorAll("#sheet-body .cat").forEach((cat) => {
    let sum = 0;
    cat.querySelectorAll(".r-amount").forEach((i) => {
      const v = amount(i.value);
      i.style.color = i.value.trim() && isNaN(v) ? "var(--neg)" : "";
      if (!isNaN(v)) sum += v;
    });
    $(".sum", cat).textContent = fmtEur(sum);
    total += sum;
  });
  $("#sheet-total").textContent = fmtEur(total);
}

function rowHtml(name = "", value = "") {
  return `<div class="row"><input class="r-name" placeholder="Asset name" value="${esc(name)}">
    <input class="r-amount" inputmode="decimal" placeholder="0" value="${esc(value)}">
    <button class="r-del" type="button" aria-label="Remove">✕</button></div>`;
}

function drawSheet() {
  const cats = [...Object.keys(sheet.categories), ...Object.keys(sheet.portfolio).filter((c) => !(c in sheet.categories))];
  $("#sheet-body").innerHTML = cats.map((c) => {
    const assets = sheet.portfolio[c] || {};
    return `<div class="cat" data-cat="${esc(c)}">
      <div class="cat-head"><span class="swatch" style="background:${esc(sheet.categories[c] || "#8B959E")}"></span>
        <span class="name">${esc(c)}</span><span class="sum"></span></div>
      <div class="rows">${Object.entries(assets).map(([n, v]) => rowHtml(n, v)).join("")}</div>
      <button class="add" type="button">+ Add asset</button></div>`;
  }).join("");
  updateTotals();
}

$("#sheet-body").addEventListener("input", updateTotals);
$("#sheet-body").addEventListener("click", (e) => {
  if (e.target.classList.contains("r-del")) { e.target.closest(".row").remove(); updateTotals(); }
  if (e.target.classList.contains("add")) {
    const rows = $(".rows", e.target.closest(".cat"));
    rows.insertAdjacentHTML("beforeend", rowHtml());
    rows.lastElementChild.querySelector(".r-name").focus();
  }
});
$("#sheet-from").addEventListener("change", (e) => openSheet(e.target.value));
$("#new-snapshot").addEventListener("click", () => openSheet());
$("#sheet-close").addEventListener("click", closeSheet);
$("#sheet-backdrop").addEventListener("click", (e) => { if (e.target.id === "sheet-backdrop") closeSheet(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#sheet-backdrop").hidden) closeSheet(); });

$("#sheet-save").addEventListener("click", async () => {
  const date = $("#sheet-date").value;
  if (!date) { $("#sheet-msg").textContent = "Pick a date first."; return; }
  const existing = [...$("#sheet-from").options].some((o) => o.value === date);
  if (existing && !confirm(`A snapshot for ${date} already exists. Replace it?`)) return;
  const r = await api("/api/snapshot", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date, portfolio: readSheet() }),
  });
  const res = await r.json();
  if (res.error) { $("#sheet-msg").textContent = res.error; return; }
  closeSheet();
  toast(`${res.replaced ? "Replaced" : "Saved"} ${res.saved}`);
  load();
});

// ---------- App switcher (top left) ----------
const appBtn = $(".app-btn"), appMenu = $(".app-menu");
const closeApps = () => { appMenu.hidden = true; appBtn.setAttribute("aria-expanded", "false"); };
appBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  appMenu.hidden = !appMenu.hidden;
  appBtn.setAttribute("aria-expanded", String(!appMenu.hidden));
});
document.addEventListener("click", (e) => { if (!e.target.closest(".switcher")) closeApps(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeApps(); });

// ---------- Settings (settings.py) ----------

// ⚙: the settings sheet shared with Gastos (settings.js)
$("#open-settings").addEventListener("click", async () => {
  try {
    const { openSettings } = await import("/static/settings.js");
    openSettings({
      app: "portfolio", accent: "var(--blue)",
      onChange(name, value) {
        if (name === "demo") return location.reload();
        if (["privacy", "motion", "chart_size"].includes(name)) applyLook({ ...look, [name]: value });
        if (name === "show_backtest") document.querySelectorAll("[data-page=backtest]").forEach((a) => (a.hidden = !value));
        // drop the page's own value for this setting (if any) so the saved one shows
        const { page, params } = route();
        if (params.has(name)) { params.delete(name); go(page, params); } else load();
      },
    });
  } catch (e) { toast(e.message, true); }
});
import("/static/settings.js").then((m) => m.reloadWhenDemoChanges()).catch(() => {});

// ---------- Keyboard (desktop): 1-4 tabs, N new snapshot, , settings, H hide amounts, Esc closes ----------
document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
  if (e.key === "Escape") {
    const full = $(".card.fullscreen");
    if (full) { full.classList.remove("fullscreen"); document.body.classList.remove("has-fullscreen"); Plotly.Plots.resize($(".chart", full)); }
    return;
  }
  const tabs = [...document.querySelectorAll("#tabs a:not([hidden])")];
  if (/^[1-9]$/.test(e.key) && tabs[+e.key - 1]) tabs[+e.key - 1].click();
  else if (e.key === "n" && !$("#new-snapshot").disabled) openSheet();
  else if (e.key === ",") $("#open-settings").click();
  else if (e.key === "h") document.documentElement.dataset.privacy = document.documentElement.dataset.privacy === "on" ? "off" : "on";
});

// ---------- Start ----------
api("/api/settings").then((r) => r.json()).then((s) => applyLook(s.values)).catch(() => {});
window.addEventListener("hashchange", load);
window.addEventListener("online", load);
load();
