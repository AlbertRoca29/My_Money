// Gastos — the screens. Data comes from store.js; this file only filters, sums and draws.
import * as store from "./store.js";

const EXPENSE_CATS = ["🛒 Groceries", "🍽️ Restaurants & Cafés", "🚌 Transportation", "🩺 Health & Personal Care",
  "🎨 Arts & Culture", "👕 Clothing", "🎉 Parties & Nightlife", "🏡 Housing", "🤷 Miscellaneous"];
const INCOME_CATS = ["💼 Job", "📈 Investments", "🎁 Gifts", "📦 Selling", "🌀 Other"];
const PALETTE = ["#0666EB", "#F5A524", "#00A86B", "#E5484D", "#8E4EC6", "#12A5B0", "#D6409F", "#7A8B99", "#C2700B",
  "#3E63DD", "#2F9E44", "#B54708"];

const state = {
  entries: [],
  month: monthKey(new Date()),   // "2026-11"
  list: { q: "", kind: "all", cat: "" },
};

// ---------------------------------------------------------------- helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const eurFmt = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });
const eur0Fmt = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const eur = (n) => eurFmt.format(n);
const eur0 = (n) => eur0Fmt.format(n);
const pct = (n) => `${Math.round(n * 100)}%`;

function monthKey(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; }
function shiftMonth(key, step) { const [y, m] = key.split("-").map(Number); return monthKey(new Date(y, m - 1 + step, 1)); }
function monthName(key, opts = { month: "long", year: "numeric" }) {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-GB", opts);
}
function dayName(iso) {
  const d = new Date(iso + "T00:00"), today = new Date();
  const diff = Math.round((new Date(today.toDateString()) - d) / 864e5);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}
const todayIso = () => new Date(Date.now() - new Date().getTimezoneOffset() * 6e4).toISOString().slice(0, 10);

const emoji = (cat) => [...(cat || "")][0] || "•";
const label = (cat) => (cat || "").replace(/^\S+\s/, "");
// Entries paid by someone else stay visible but never count towards a total.
const counts = (e) => !e.paid_by_other;

function categories(kind) {
  const base = kind === "income" ? INCOME_CATS : EXPENSE_CATS;
  const extra = [...new Set(state.entries.filter((e) => e.kind === kind).map((e) => e.category))].filter((c) => !base.includes(c));
  return [...base, ...extra];
}
const colorOf = (cat) => {
  const all = [...EXPENSE_CATS, ...INCOME_CATS];
  const i = all.indexOf(cat);
  return PALETTE[(i < 0 ? [...cat].reduce((a, c) => a + c.codePointAt(0), 0) : i) % PALETTE.length];
};

function totals(entries) {
  let spent = 0, income = 0;
  for (const e of entries) {
    if (e.kind === "income") income += e.amount;
    else if (counts(e)) spent += e.amount;
  }
  return { spent, income, saved: income - spent, rate: income ? (income - spent) / income : null };
}
const inMonth = (key) => state.entries.filter((e) => e.date.startsWith(key));

function sumBy(entries, keyFn) {
  const m = new Map();
  for (const e of entries) m.set(keyFn(e), (m.get(keyFn(e)) || 0) + e.amount);
  return [...m].sort((a, b) => b[1] - a[1]);
}

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("error", isError);
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 2600);
}

// ---------------------------------------------------------------- pieces
function row(e) {
  const sign = e.kind === "income" ? "+" : "−";
  const cls = e.kind === "income" ? "pos" : counts(e) ? "" : "other";
  return `<button class="row" data-id="${esc(e.id)}">
    <span class="avatar" style="--c:${colorOf(e.category)}">${esc(emoji(e.category))}</span>
    <span class="row-main">
      <span class="row-name">${esc(e.name)}${e.receipt ? ' <span class="clip" title="Has receipt">📎</span>' : ""}</span>
      <span class="row-sub">${esc(label(e.category))}</span>
    </span>
    <span class="row-amt ${cls}">${sign}${eur(e.amount)}</span>
  </button>`;
}

function catBars(pairs, total) {
  if (!pairs.length) return `<p class="empty">Nothing yet.</p>`;
  const max = pairs[0][1];
  return `<div class="bars">${pairs.map(([cat, v]) => `
    <div class="bar-row">
      <span class="bar-label">${esc(emoji(cat))} ${esc(label(cat))}</span>
      <span class="bar-val">${eur0(v)} <span class="muted">${pct(v / total)}</span></span>
      <span class="bar-track"><span class="bar-fill" style="width:${(v / max) * 100}%;background:${colorOf(cat)}"></span></span>
    </div>`).join("")}</div>`;
}

// Grouped bars (income vs spent), one fixed-width slot per month so the whole history fits in a
// horizontally scrolling strip. Tapping a month opens it on Home.
function monthChart(months) {
  const slot = 30, bw = 10, H = 180, pad = { t: 10, b: 36 };
  const W = slot * months.length;
  const max = Math.max(1, ...months.flatMap((m) => [m.income, m.spent]));
  const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const now = monthKey(new Date());
  const bars = months.map((m, i) => {
    const x = i * slot + slot / 2;
    const year = i === 0 || m.key.endsWith("-01") ? `<text x="${x}" y="${H - 6}" text-anchor="middle" class="yr">${m.key.slice(0, 4)}</text>` : "";
    return `<g class="mbar" data-month="${m.key}">
      <rect class="hit" x="${x - slot / 2}" y="0" width="${slot}" height="${H - pad.b + 16}" rx="6" fill="transparent"/>
      <rect x="${x - bw - 1}" y="${y(m.income)}" width="${bw}" height="${H - pad.b - y(m.income)}" rx="2" fill="var(--pos)"/>
      <rect x="${x + 1}" y="${y(m.spent)}" width="${bw}" height="${H - pad.b - y(m.spent)}" rx="2" fill="var(--neg)"/>
      <text x="${x}" y="${H - pad.b + 14}" text-anchor="middle" class="${m.key === now ? "cur" : ""}">${monthName(m.key, { month: "narrow" })}</text>${year}
      <title>${monthName(m.key)} — income ${eur0(m.income)}, spent ${eur0(m.spent)}</title>
    </g>`;
  }).join("");
  return `<div class="chart-scroll"><svg class="chart" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Income and spending per month">
    <line x1="0" x2="${W}" y1="${H - pad.b}" y2="${H - pad.b}" stroke="var(--line)"/>${bars}</svg></div>
    <div class="legend"><span><i style="background:var(--pos)"></i>Income</span><span><i style="background:var(--neg)"></i>Spent</span><span class="muted">Scroll left for earlier months</span></div>`;
}

// ---------------------------------------------------------------- views
const views = {
  home() {
    const month = inMonth(state.month);
    const t = totals(month);
    // For the month in progress, compare with what earlier months had spent by the same day.
    const today = todayIso();
    const upTo = state.month === today.slice(0, 7) ? today.slice(8) : "31";
    const prev = Array.from({ length: 6 }, (_, i) => totals(inMonth(shiftMonth(state.month, -i - 1))
      .filter((e) => e.date.slice(8) <= upTo)).spent).filter((v) => v > 0);
    const avg = prev.length ? prev.reduce((a, b) => a + b, 0) / prev.length : null;
    const vs = avg ? (t.spent - avg) / avg : null;
    const avgLabel = upTo === "31" ? "6-month average" : `usual by day ${Number(upTo)}`;
    const byCat = sumBy(month.filter((e) => e.kind === "expense" && counts(e)), (e) => e.category);
    return `
      <div class="wide split"><section class="hero">
        <div class="eyebrow">Spent in ${esc(monthName(state.month, { month: "long" }))}</div>
        <div class="big">${eur(t.spent)}</div>
        ${vs === null ? "" : `<div class="delta ${vs > 0 ? "neg" : "pos"}">${vs > 0 ? "▲" : "▼"} ${pct(Math.abs(vs))} vs ${avgLabel} (${eur0(avg)})</div>`}
      </section>
      <section class="tiles">
        <div class="tile"><span>Income</span><b class="pos">${eur0(t.income)}</b></div>
        <div class="tile"><span>Saved</span><b class="${t.saved < 0 ? "neg" : ""}">${eur0(t.saved)}</b></div>
        <div class="tile"><span>Savings rate</span><b>${t.rate === null ? "—" : pct(t.rate)}</b></div>
      </section></div>
      <section class="card"><h2>By category</h2>${catBars(byCat, t.spent)}</section>
      <section class="card">
        <h2>Latest <a href="#list" class="link">See all</a></h2>
        ${month.length ? `<div class="rows">${month.slice(0, 6).map(row).join("")}</div>` : `<p class="empty">No movements this month. Tap + to add one.</p>`}
      </section>`;
  },

  list() {
    const { q, kind, cat } = state.list;
    const needle = q.trim().toLowerCase();
    // A search looks through every month; otherwise only the selected one.
    let items = needle ? state.entries.filter((e) => `${e.name} ${e.category} ${e.note || ""}`.toLowerCase().includes(needle)) : inMonth(state.month);
    // Expenses paid by others are listed (struck through) but never added to a total.
    if (kind === "expense") items = items.filter((e) => e.kind === "expense");
    if (kind === "income") items = items.filter((e) => e.kind === "income");
    if (cat) items = items.filter((e) => e.category === cat);
    const t = totals(items);
    const days = Map.groupBy ? Map.groupBy(items, (e) => e.date) : items.reduce((m, e) => m.set(e.date, [...(m.get(e.date) || []), e]), new Map());
    const chip = (k, txt) => `<button class="chip ${kind === k ? "on" : ""}" data-kind="${k}">${txt}</button>`;
    return `
      <div class="filters">
        <input id="q" type="search" placeholder="Search all months…" value="${esc(q)}" autocomplete="off">
        <div class="chips">${chip("all", "All")}${chip("expense", "Expenses")}${chip("income", "Income")}</div>
        <select id="cat"><option value="">All categories</option>
          ${[...categories("expense"), ...categories("income")].map((c) => `<option ${c === cat ? "selected" : ""}>${esc(c)}</option>`).join("")}
        </select>
      </div>
      <div class="days">
      <p class="summary">${items.length} movements${needle ? " (all months)" : ""} · spent <b>${eur(t.spent)}</b> · income <b class="pos">${eur(t.income)}</b></p>
      ${items.length ? [...days].map(([day, es]) => {
        const net = totals(es);
        return `<section class="day"><h3>${esc(dayName(day))}<span>${net.spent ? "−" + eur(net.spent) : ""}</span></h3>
          <div class="rows">${es.map(row).join("")}</div></section>`;
      }).join("") : `<p class="empty">Nothing matches.</p>`}
      </div>`;
  },

  // Stats always cover the last 12 months up to today; the chart scrolls back through all history.
  stats() {
    const now = monthKey(new Date());
    const keys = Array.from({ length: 12 }, (_, i) => shiftMonth(now, i - 11));
    const months = keys.map((key) => ({ key, ...totals(inMonth(key)) }));
    const first = state.entries.at(-1)?.date.slice(0, 7) || now;
    const history = [];
    for (let k = first; k <= now; k = shiftMonth(k, 1)) history.push({ key: k, ...totals(inMonth(k)) });
    const active = months.filter((m) => m.spent || m.income);
    const n = active.length || 1;
    const sum = (f) => active.reduce((a, m) => a + m[f], 0);
    const range = state.entries.filter((e) => e.date >= keys[0] && e.date.slice(0, 7) <= now);
    const spentAll = range.filter((e) => e.kind === "expense" && counts(e));
    const byCat = sumBy(spentAll, (e) => e.category).map(([c, v]) => [c, v / n]);
    const places = [...spentAll.reduce((m, e) => {
      const k = e.name.trim().toLowerCase();
      const p = m.get(k) || { name: e.name, cat: e.category, total: 0, n: 0 };
      p.total += e.amount; p.n += 1;
      return m.set(k, p);
    }, new Map()).values()].sort((a, b) => b.total - a.total).slice(0, 10);
    const income = sumBy(range.filter((e) => e.kind === "income"), (e) => e.category);
    const incomeTotal = income.reduce((a, [, v]) => a + v, 0);
    return `
      <p class="summary wide">Last 12 months, up to ${esc(monthName(now))}</p>
      <section class="tiles wide">
        <div class="tile"><span>Avg spent / month</span><b>${eur0(sum("spent") / n)}</b></div>
        <div class="tile"><span>Avg income / month</span><b class="pos">${eur0(sum("income") / n)}</b></div>
        <div class="tile"><span>Savings rate</span><b>${sum("income") ? pct((sum("income") - sum("spent")) / sum("income")) : "—"}</b></div>
      </section>
      <section class="card wide"><h2>Income vs spent</h2>${monthChart(history)}</section>
      <section class="card"><h2>Average per month by category</h2>${catBars(byCat, byCat.reduce((a, [, v]) => a + v, 0))}</section>
      <section class="card"><h2>Where the money goes</h2>
        ${places.length ? `<ol class="places">${places.map((p) => `<li><span>${esc(emoji(p.cat))} ${esc(p.name)} <span class="muted">×${p.n}</span></span><b>${eur0(p.total)}</b></li>`).join("")}</ol>` : `<p class="empty">Nothing yet.</p>`}
      </section>
      <section class="card"><h2>Income sources</h2>${catBars(income, incomeTotal)}</section>`;
  },

  settings() {
    const first = state.entries.at(-1)?.date, last = state.entries[0]?.date;
    return `
      <section class="card"><h2>Data</h2>
        <p>${state.entries.length} movements${first ? `, from ${esc(first)} to ${esc(last)}` : ""}.</p>
        <div class="actions">
          <button class="pill dark" id="import">Import from Google Sheet</button>
          <a class="pill" href="${store.exportUrl}" download>Export CSV</a>
        </div>
        <p class="muted small">The import reads the GASTOS and INGRESOS tabs of the Google Sheet. Rows already here are
          updated by ID; movements you added in this app are never touched, so it is safe to run again.</p>
      </section>
      <section class="card"><h2>On your phone</h2>
        <p class="small">Start the server with <code>MY_MONEY_HOST=0.0.0.0</code>, open this page from your phone on the same
          Wi-Fi, then use <b>Add to Home Screen</b>. It opens like an app and shows the last data it saw when offline.</p>
      </section>`;
  },
};

// ---------------------------------------------------------------- add / edit sheet
// Amounts accept sums like "12,5 + 3.20".
function parseAmount(text) {
  const expr = String(text).replace(/,/g, ".").replace(/\s/g, "");
  if (!expr || !/^[\d.+\-*/()]+$/.test(expr)) return NaN;
  try { return Math.round(Function(`"use strict";return (${expr})`)() * 100) / 100; } catch { return NaN; }
}

function openSheet(entry = null) {
  const e = entry || { kind: "expense", name: "", category: "", date: todayIso(), amount: "", gross: "", paid_by_other: false, note: "" };
  const dlg = $("#sheet");
  let kind = e.kind, category = e.category, receipt = e.receipt || null, receiptFile = null, catTouched = !!entry;

  const names = (k) => [...new Set(state.entries.filter((x) => x.kind === k).map((x) => x.name))].slice(0, 400);
  const lastCat = (name) => state.entries.find((x) => x.kind === kind && x.name.toLowerCase() === name.trim().toLowerCase())?.category;

  function draw() {
    const url = store.receiptUrl(receipt);
    dlg.innerHTML = `<form method="dialog" class="sheet-body" novalidate>
      <div class="grab"></div>
      <div class="seg">
        <button type="button" data-k="expense" class="${kind === "expense" ? "on" : ""}">Expense</button>
        <button type="button" data-k="income" class="${kind === "income" ? "on" : ""}">Income</button>
      </div>
      <input class="amount" name="amount" inputmode="decimal" placeholder="0,00 €" value="${esc(e.amount)}" autocomplete="off" required>
      <input name="name" list="names" placeholder="${kind === "income" ? "From…" : "Where / what…"}" value="${esc(e.name)}" autocomplete="off" required>
      <datalist id="names">${names(kind).map((n) => `<option value="${esc(n)}">`).join("")}</datalist>
      <div class="cats">${categories(kind).map((c) => `<button type="button" class="cat ${c === category ? "on" : ""}" data-cat="${esc(c)}" style="--c:${colorOf(c)}">${esc(emoji(c))}<span>${esc(label(c))}</span></button>`).join("")}</div>
      <div class="grid2">
        <label>Date<input type="date" name="date" value="${esc(e.date)}" required></label>
        ${kind === "income"
          ? `<label>Gross (before tax)<input name="gross" inputmode="decimal" placeholder="optional" value="${esc(e.gross ?? "")}"></label>`
          : `<label class="switch"><input type="checkbox" name="paid_by_other" ${e.paid_by_other ? "checked" : ""}><span>Paid by others<small>job, family… not counted</small></span></label>`}
      </div>
      <input name="note" placeholder="Note (optional)" value="${esc(e.note ?? "")}">
      ${kind === "expense" ? `<label class="receipt">📎 ${receiptFile ? esc(receiptFile.name) : url ? `<a href="${url}" target="_blank">View receipt</a> · replace` : receipt ? "Receipt kept in Google Drive · replace" : "Add receipt photo"}
        <input type="file" name="receipt" accept="image/*,application/pdf" hidden></label>` : ""}
      <p class="form-error" hidden></p>
      <div class="sheet-actions">
        ${entry ? `<button type="button" class="pill danger" id="del">Delete</button>` : ""}
        <button type="button" class="pill" id="cancel">Cancel</button>
        <button type="submit" class="pill dark" id="save">${entry ? "Save" : "Add"}</button>
      </div>
    </form>`;
  }

  // Keep what was typed when the sheet redraws (switching kind, picking a receipt).
  function capture() {
    const f = $("form", dlg);
    if (!f) return;
    Object.assign(e, { amount: f.amount.value, name: f.name.value, date: f.date.value, note: f.note.value });
    if (f.gross) e.gross = f.gross.value;
    if (f.paid_by_other) e.paid_by_other = f.paid_by_other.checked;
  }

  dlg.onclick = async (ev) => {
    if (ev.target === dlg) return dlg.close();          // tap on the backdrop
    const btn = ev.target.closest("button");
    if (!btn) return;
    if (btn.dataset.k && btn.dataset.k !== kind) {
      capture(); kind = btn.dataset.k; category = ""; catTouched = false; draw();
      $("[name=amount]", dlg).focus();
    } else if (btn.dataset.cat) {
      category = btn.dataset.cat; catTouched = true;
      dlg.querySelectorAll(".cat").forEach((b) => b.classList.toggle("on", b === btn));
    } else if (btn.id === "cancel") dlg.close();
    else if (btn.id === "del" && confirm(`Delete “${e.name}”?`)) {
      try { await store.deleteEntry(e.id); dlg.close(); toast("Deleted"); await reload(); }
      catch (err) { toast(err.message, true); }
    }
  };
  dlg.oninput = (ev) => {
    if (ev.target.name === "name" && !catTouched) {
      const c = lastCat(ev.target.value);
      if (c) { category = c; dlg.querySelectorAll(".cat").forEach((b) => b.classList.toggle("on", b.dataset.cat === c)); }
    }
  };
  dlg.onchange = (ev) => {
    if (ev.target.name === "receipt" && ev.target.files[0]) { capture(); receiptFile = ev.target.files[0]; draw(); }
  };
  dlg.onsubmit = async (ev) => {
    ev.preventDefault();
    capture();
    const err = $(".form-error", dlg);
    const amount = parseAmount(e.amount);
    const problem = !(amount > 0) ? "Enter an amount (sums like 12,5+3 work)"
      : !e.name.trim() ? "Enter a name" : !category ? "Pick a category" : !e.date ? "Pick a date" : null;
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    $("#save", dlg).disabled = true;
    try {
      if (receiptFile) receipt = await store.uploadReceipt(receiptFile);
      const gross = kind === "income" && e.gross ? parseAmount(e.gross) : null;
      await store.saveEntry({ id: entry?.id, kind, name: e.name, category, date: e.date, amount, gross,
        paid_by_other: kind === "expense" && e.paid_by_other, receipt, note: e.note });
      dlg.close();
      toast(entry ? "Saved" : `Added ${eur(amount)}`);
      state.month = e.date.slice(0, 7);
      await reload();
    } catch (x) {
      err.textContent = x.message; err.hidden = false; $("#save", dlg).disabled = false;
    }
  };

  draw();
  dlg.showModal();
  if (!entry) $("[name=amount]", dlg).focus();
}

// ---------------------------------------------------------------- routing
function route() { return (location.hash.slice(1) || "home").split("?")[0]; }

function render() {
  const r = views[route()] ? route() : "home";
  $("#view").innerHTML = views[r]();
  $("#view").dataset.view = r;
  document.querySelectorAll("[data-tab]").forEach((a) => a.classList.toggle("active", a.dataset.tab === r));
  $("#month").hidden = r === "settings" || r === "stats";
  $("#month-label").textContent = monthName(state.month, { month: "short", year: "numeric" });
  const strip = $(".chart-scroll");
  if (strip) strip.scrollLeft = strip.scrollWidth;   // start at the latest month
}

async function reload() {
  try {
    const { entries, offline } = await store.listEntries();
    state.entries = entries;
    const b = $("#banner");
    b.hidden = !offline;
    b.textContent = offline ? "Offline — showing the last data seen. Changes can't be saved until you're back online." : "";
  } catch (err) {
    toast(`Could not load data: ${err.message}`, true);
  }
  render();
}

// One set of listeners for everything drawn inside #view.
$("#view").addEventListener("click", async (ev) => {
  const rowBtn = ev.target.closest(".row");
  if (rowBtn) return openSheet(state.entries.find((e) => e.id === rowBtn.dataset.id));
  const chip = ev.target.closest(".chip");
  if (chip) { state.list.kind = chip.dataset.kind; return render(); }
  const bar = ev.target.closest(".mbar");
  if (bar) { state.month = bar.dataset.month; location.hash = "home"; return; }
  if (ev.target.id === "import") {
    ev.target.disabled = true; ev.target.textContent = "Importing…";
    try { const r = await store.importSheet(); toast(`${r.rows} rows read, ${r.new} new`); await reload(); }
    catch (err) { toast(err.message, true); render(); }
  }
});
$("#view").addEventListener("input", (ev) => {
  if (ev.target.id !== "q") return;
  state.list.q = ev.target.value;
  const pos = ev.target.selectionStart;
  render();
  const q = $("#q"); q.focus(); q.setSelectionRange(pos, pos);
});
$("#view").addEventListener("change", (ev) => {
  if (ev.target.id === "cat") { state.list.cat = ev.target.value; render(); }
});
$("#month").addEventListener("click", (ev) => {
  const step = Number(ev.target.dataset.step);
  if (step) { state.month = shiftMonth(state.month, step); render(); }
});
$("#add").addEventListener("click", () => openSheet());
$("#add-top").addEventListener("click", () => openSheet());
window.addEventListener("hashchange", () => { render(); scrollTo(0, 0); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
reload();
