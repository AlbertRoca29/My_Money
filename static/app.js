// My Money — browser side.
// This file has no finance logic: it asks the Python server for a page (/api/page/<name>) and draws
// the blocks it gets back (see web/blocks.py for the list). To change what a page shows, edit Python.

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };
const PHONE = window.matchMedia("(max-width: 640px)");

// The Python figures are drawn for a desktop card. On a phone: no drag-to-zoom (so a swipe scrolls
// the page), fewer date ticks, smaller fonts, and side-by-side subplots get a wider, scrollable canvas.
// Returns true when the figure should be drawn wider than the screen.
function fitPhone(fig) {
  const l = fig.layout;
  l.dragmode = false;
  l.legend = { ...l.legend, font: { ...(l.legend || {}).font, size: 11 } };
  const dateAxes = new Set(fig.data.filter((t) => Array.isArray(t.x) && /^\d{4}-\d\d/.test(t.x[0])).map((t) => t.xaxis || "x"));
  const pies = fig.data.filter((t) => t.type === "pie" && t.domain && t.domain.x);
  if (pies.length > 2) {
    // a grid of donuts (one per fund): two per row, the subplot titles follow their donut
    const rows = Math.ceil(pies.length / 2), titles = l.annotations || [];
    pies.forEach((t, i) => {
      const c = i % 2, r = Math.floor(i / 2);
      t.domain = { x: [c / 2 + 0.03, (c + 1) / 2 - 0.03], y: [1 - (r + 1) / rows + 0.04 / rows, 1 - r / rows - 0.12 / rows] };
      if (titles[i]) Object.assign(titles[i], { x: (c + 0.5) / 2, y: 1 - r / rows - 0.1 / rows, yanchor: "bottom", font: { ...titles[i].font, size: 11 } });
    });
    l.height = 210 * rows;
  }
  let wide = pies.length <= 2 && pies.some((t) => t.domain.x[1] - t.domain.x[0] < 0.9);
  if (fig.data.some((t) => t.type === "heatmap" && Array.isArray(t.x) && t.x.length > 4)) wide = true; // one column per fund
  for (const k of Object.keys(l).filter((k) => /^[xy]axis\d*$/.test(k))) {
    const ax = l[k];
    ax.fixedrange = true;
    ax.tickfont = { ...ax.tickfont, size: 10 };
    if (k[0] === "x" && ax.domain && ax.domain[1] - ax.domain[0] < 0.9) wide = true;
    if (k[0] === "x" && dateAxes.has(k.replace("axis", ""))) ax.nticks = 5;
  }
  return wide;
}

// fetch, except that a signed-out (or expired) session goes back to the sign-in page
async function api(url, options) {
  const r = await fetch(url, options);
  if (r.status === 401) { location.href = "/login?next=/portfolio"; throw new Error("Signing in…"); }
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
  document.querySelectorAll("#tabs a, #tabbar a").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
  const tab = $("#tabs a.active"), tabs = $("#tabs");
  if (tab) tabs.scrollTo({ left: tab.offsetLeft - (tabs.clientWidth - tab.offsetWidth) / 2, behavior: "smooth" });
  const token = ++loadToken;
  showSkeleton();
  let res;
  try {
    // phone=1: the Python pages then stack side-by-side charts and show fewer rows
    const query = new URLSearchParams(params);
    if (PHONE.matches) query.set("phone", "1");
    const r = await api(`/api/page/${page}?${query}`);
    res = await r.json();
  } catch (e) {
    res = { error: `Could not reach the server (${e.message}). Is app.py running?` };
  }
  if (token !== loadToken) return; // the user already moved on to another page
  render(page, params, res);
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
  card.className = `card ${s.width === "half" ? "half" : ""} ${s.error ? "error" : ""}`;
  card.id = s.id;
  card.innerHTML = `<h2>${esc(s.title)}</h2>${s.subtitle ? `<p class="sub">${esc(s.subtitle)}</p>` : ""}<div class="body"></div>`;
  const body = $(".body", card);
  if (s.error) { body.textContent = s.error; return card; }
  for (const b of s.blocks || []) {
    const draw = BLOCKS[b.type];
    if (draw) draw(body, b);
  }
  return card;
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
    if (PHONE.matches && fitPhone(fig)) {
      const scroll = document.createElement("div");
      scroll.className = "chart-scroll";
      el.classList.add("wide");
      scroll.appendChild(el);
      body.appendChild(scroll);
    } else {
      body.appendChild(el);
    }
    // wait until the card is in the page so Plotly can measure the width
    requestAnimationFrame(() => {
      Plotly.newPlot(el, fig.data, fig.layout, PLOTLY_CONFIG).then(() => {
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

// ---------- Settings (settings.py; Gastos shows its own group in its Settings tab) ----------
function applyNav(nav) {
  document.documentElement.dataset.nav = nav || "top";
  try { localStorage.setItem("mymoney.nav", nav || "top"); } catch {}
}

function settingRow(f, v) {
  const text = `<span>${esc(f.label)}${f.help ? `<small>${esc(f.help)}</small>` : ""}</span>`;
  const n = `data-setting="${esc(f.name)}"`;
  if (f.type === "toggle") return `<label class="set-row">${text}<span class="field switch"><input type="checkbox" ${n} ${v ? "checked" : ""}><i></i></span></label>`;
  if (f.type === "select") return `<label class="set-row">${text}<select ${n}>${f.options.map((o) =>
    `<option value="${esc(o.value)}" ${o.value === String(v) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select></label>`;
  if (f.type === "number") return `<label class="set-row">${text}<input type="number" ${n} value="${esc(v)}" min="${f.min ?? ""}" max="${f.max ?? ""}" step="${f.step ?? 1}" inputmode="decimal"></label>`;
  return `<label class="set-row">${text}<input type="${esc(f.type)}" ${n} value="${esc(v)}"></label>`;
}

async function openSettings() {
  const { values, fields } = await (await api("/api/settings")).json();
  const groups = [...new Set(fields.map((f) => f.group))].filter((g) => g !== "Gastos");
  $("#settings-body").innerHTML = groups.map((g) => `<section class="set-group"><h3>${esc(g)}</h3><div class="set-list">
    ${fields.filter((f) => f.group === g).map((f) => settingRow(f, values[f.name])).join("")}</div></section>`).join("");
  $("#settings-backdrop").hidden = false;
  document.body.style.overflow = "hidden";
}

function closeSettings() {
  $("#settings-backdrop").hidden = true;
  document.body.style.overflow = "";
}

$("#settings-body").addEventListener("change", async (e) => {
  const name = e.target.dataset.setting;
  if (!name) return;
  const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
  if (name === "nav") applyNav(value);
  const res = await (await api("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [name]: value }),
  })).json();
  if (res.error) return toast(res.error, true);
  toast("Saved");
  // drop the page's own value for this setting (if any) so the saved one shows
  const { page, params } = route();
  if (params.has(name)) { params.delete(name); go(page, params); } else load();
});
$("#open-settings").addEventListener("click", openSettings);
$("#settings-close").addEventListener("click", closeSettings);
$("#settings-backdrop").addEventListener("click", (e) => { if (e.target.id === "settings-backdrop") closeSettings(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#settings-backdrop").hidden) closeSettings(); });
api("/api/settings").then((r) => r.json()).then((s) => applyNav(s.values.nav)).catch(() => {});

// ---------- Start ----------
window.addEventListener("hashchange", load);
PHONE.addEventListener("change", load); // redraw the charts when crossing the phone / desktop width
load();
