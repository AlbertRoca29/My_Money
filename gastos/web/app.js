// Gastos — the screens. Data comes from store.js; this file only filters, sums and draws.
import * as store from "./store.js";

const EXPENSE_CATS = ["🛒 Groceries", "🍽️ Restaurants & Cafés", "🚌 Transportation", "🩺 Health & Personal Care",
  "🎨 Arts & Culture", "👕 Clothing", "🎉 Parties & Nightlife", "🏡 Housing", "🤷 Miscellaneous"];
const INCOME_CATS = ["💼 Job", "📈 Investments", "🎁 Gifts", "📦 Selling", "🌀 Other"];
const EARN_MIN = 30;   // Home lists income entries above this (€)
const PALETTE = ["#0666EB", "#F5A524", "#00A86B", "#E5484D", "#8E4EC6", "#12A5B0", "#D6409F", "#7A8B99", "#C2700B",
  "#3E63DD", "#2F9E44", "#B54708"];

const state = {
  entries: [],
  month: monthKey(new Date()),   // "2026-11"
  list: { q: "", kind: "all", cat: "", sort: "date", catOpen: false },
  period: "12m",                 // Stats: "12m" (last 12 months) or a year, "2025"
  settings: {},                  // ../../settings.py values (hide_others, top_min, nav…)
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
  // en-GB spells September "Sept" when short; en-US gives the usual "Sep"
  return new Date(y, m - 1, 1).toLocaleDateString(opts.month === "short" ? "en-US" : "en-GB", opts);
}
// "Nov 26": short month and two-digit year, for the month picker
function monthShort(key) { return `${monthName(key, { month: "short" })} ${key.slice(2, 4)}`; }
function dayName(iso) {
  const d = new Date(iso + "T00:00"), today = new Date();
  const diff = Math.round((new Date(today.toDateString()) - d) / 864e5);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}
// today (or today +/- n days) as YYYY-MM-DD, in local time
const dayIso = (n = 0) => new Date(Date.now() + n * 864e5 - new Date().getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
const todayIso = () => dayIso(0);

const emoji = (cat) => [...(cat || "")][0] || "•";
const label = (cat) => (cat || "").replace(/^\S+\s/, "");
// Entries paid by someone else stay visible but never count towards a total.
const counts = (e) => !e.paid_by_other;
// Settings can hide them altogether (Movements and Home).
const shown = (e) => !(e.paid_by_other && state.settings.hide_others);

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

// Stats periods: the last 12 months, or one calendar year. Returns the 12 month keys.
function periodMonths(period) {
  if (period !== "12m") return Array.from({ length: 12 }, (_, i) => `${period}-${String(i + 1).padStart(2, "0")}`);
  const now = monthKey(new Date());
  return Array.from({ length: 12 }, (_, i) => shiftMonth(now, i - 11));
}
const years = () => [...new Set(state.entries.map((e) => e.date.slice(0, 4)))].sort().reverse();

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
function row(e, withDate = false) {
  const loss = e.kind === "income" && e.amount < 0;   // a negative income is a loss
  const sign = e.kind === "income" ? (loss ? "−" : "+") : "−";
  const cls = loss ? "neg" : e.kind === "income" ? "pos" : counts(e) ? "" : "other";
  return `<button class="row" data-id="${esc(e.id)}">
    <span class="avatar" style="--c:${colorOf(e.category)}">${esc(emoji(e.category))}</span>
    <span class="row-main">
      <span class="row-name">${esc(e.name)}${e.receipt ? ' <span class="clip" title="Has receipt">📎</span>' : ""}</span>
      <span class="row-sub">${esc(label(e.category))}${withDate ? ` · ${esc(dayName(e.date))}` : ""}</span>
    </span>
    <span class="row-amt ${cls}">${sign}${eur(Math.abs(e.amount))}</span>
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

// Grouped bars (income vs spent), one slot per month, stretched to the card's width. Tapping a month opens it on Home.
// Gridline values 0..top, at most 4 steps, on round numbers (the axis never goes below €500, so a quiet month stays small).
function niceTicks(max) {
  const raw = Math.max(max, 500) / 3, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw);
  return Array.from({ length: Math.ceil(Math.max(max, 500) / step) + 1 }, (_, i) => i * step);
}
const compact = (v) => (v >= 1000 ? `${+(v / 1000).toFixed(1)}k` : String(v));

function monthChart(months) {
  const slot = 30, bw = 9, H = 170, pad = { t: 10, b: 24, l: 26 };
  const W = pad.l + slot * months.length;
  const ticks = niceTicks(Math.max(...months.flatMap((m) => [m.income, m.spent])));
  const max = ticks.at(-1);
  const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const now = monthKey(new Date());
  const grid = ticks.map((v) => `<line x1="${pad.l}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/>
    <text x="${pad.l - 5}" y="${y(v) + 3}" text-anchor="end">${compact(v)}</text>`).join("");
  const bars = months.map((m, i) => {
    const x = pad.l + i * slot + slot / 2;
    return `<g class="mbar" data-month="${m.key}">
      <rect class="hit" x="${x - slot / 2}" y="0" width="${slot}" height="${H}" rx="6" fill="transparent"/>
      <rect x="${x - bw - 1}" y="${y(m.income)}" width="${bw}" height="${H - pad.b - y(m.income)}" rx="2" fill="var(--pos)"/>
      <rect x="${x + 1}" y="${y(m.spent)}" width="${bw}" height="${H - pad.b - y(m.spent)}" rx="2" fill="var(--neg)"/>
      <text x="${x}" y="${H - 6}" text-anchor="middle" class="${m.key === now ? "cur" : ""}">${monthName(m.key, { month: "narrow" })}</text>
      <title>${monthName(m.key)} — income ${eur0(m.income)}, spent ${eur0(m.spent)}</title>
    </g>`;
  }).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Income and spending per month">
    ${grid}${bars}</svg>
    <div class="legend"><span><i style="background:var(--pos)"></i>Income</span><span><i style="background:var(--neg)"></i>Spent</span><span class="muted">Tap a month to open it</span></div>`;
}

// The month's spending as one stacked bar, then the biggest categories (the rest summed as "Other").
function catStack(pairs, total) {
  if (!pairs.length) return `<p class="empty">Nothing spent yet.</p>`;
  const top = pairs.slice(0, 5), rest = pairs.slice(5).reduce((a, [, v]) => a + v, 0);
  const parts = [...top.map(([c, v]) => [label(c), v, colorOf(c)]), ...(rest ? [["Other", rest, "#C9CED4"]] : [])];
  return `<div class="stack">${parts.map(([, v, c]) => `<i style="flex:${v};background:${c}"></i>`).join("")}</div>
    <div class="legend-list">${parts.map(([n, v, c]) => `<div><i style="background:${c}"></i><span>${esc(n)}</span><b>${eur0(v)}</b><em>${pct(v / total)}</em></div>`).join("")}</div>`;
}

// Names are compared without case, accents, punctuation or emoji: "T-SHIRT 👕" and "t shirt" are the same.
const norm = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
function distance(a, b) {
  if (Math.abs(a.length - b.length) > 2) return 3;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return prev[b.length];
}
// Names of one kind with how many entries use each, most used first.
function nameList(kind) {
  const counts = new Map();
  for (const e of state.entries) if (e.kind === kind) counts.set(e.name, (counts.get(e.name) || 0) + 1);
  return [...counts].map(([name, n]) => ({ name, n, key: norm(name) })).filter((x) => x.key).sort((a, b) => b.n - a.n);
}

// Movements' category filter: a button that opens a menu (a native <select> looks different on every phone).
function catPicker(kind, cat) {
  const item = (value, c, text) => `<button type="button" class="catopt ${value === cat ? "on" : ""}" data-cat="${esc(value)}">
    <span class="avatar sm" style="--c:${c ? colorOf(c) : "var(--ink-2)"}">${c ? esc(emoji(c)) : "✦"}</span><span>${esc(text)}</span>
    ${value === cat ? '<svg class="tick"><use href="#i-check"/></svg>' : ""}</button>`;
  const group = (k, title) => `${title ? `<div class="cathead">${title}</div>` : ""}${categories(k).map((c) => item(c, c, label(c))).join("")}`;
  const all = kind === "income" ? "All income" : kind === "expense" ? "All expenses" : "All categories";
  const menu = kind === "all" ? group("expense", "Expenses") + group("income", "Income") : group(kind);
  return `<div class="catpick">
    <button type="button" class="catbtn ${cat ? "set" : ""}" id="cat-btn" aria-haspopup="listbox" aria-expanded="${state.list.catOpen}">
      ${cat ? `<span class="avatar sm" style="--c:${colorOf(cat)}">${esc(emoji(cat))}</span><span>${esc(label(cat))}</span>` : `<span>${all}</span>`}
      <svg class="chev"><use href="#i-chevron"/></svg>
    </button>
    ${state.list.catOpen ? `<div class="catmenu" role="listbox">${item("", null, all)}${menu}</div>` : ""}
  </div>`;
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
    const avgLabel = upTo === "31" ? "the 6-month average" : `usual by day ${Number(upTo)}`;
    const byCat = sumBy(month.filter((e) => e.kind === "expense" && counts(e)), (e) => e.category);
    // The 3 biggest expenses; a 4th and 5th only when they are above the limit in Settings.
    const minTop = Number(state.settings.top_min ?? 30);
    const top = month.filter((e) => e.kind === "expense" && counts(e)).sort((a, b) => b.amount - a.amount)
      .filter((e, i) => i < 3 || e.amount > minTop).slice(0, 5);
    // The biggest income entries (and losses, which are negative income), only the ones above EARN_MIN in size
    const earned = month.filter((e) => e.kind === "income" && Math.abs(e.amount) > EARN_MIN)
      .sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount)).slice(0, 5);
    return `
      <div class="wide">
        <section class="hero">
          <div class="eyebrow">Spent in ${esc(monthName(state.month, { month: "long" }))}</div>
          <div class="big">${eur(t.spent)}</div>
          ${vs === null ? "" : `<div class="delta"><b class="${vs > 0 ? "neg" : "pos"}">${vs > 0 ? "+" : "−"}${pct(Math.abs(vs))}</b> vs ${avgLabel}</div>`}
        </section>
        <div class="duo">
          <div><span>Income</span><b class="pos">${eur0(t.income)}</b></div>
          <div><span>Saved</span><b class="${t.saved < 0 ? "neg" : ""}">${eur0(t.saved)}${t.rate === null ? "" : `<small>${pct(t.rate)}</small>`}</b></div>
        </div>
      </div>
      <section class="card"><h2>Where it went</h2>${catStack(byCat, t.spent)}</section>
      <section class="card">
        <h2>Biggest expenses <a href="#list" class="link">See all</a></h2>
        ${top.length ? `<div class="rows">${top.map((e) => row(e)).join("")}</div>` : `<p class="empty">Nothing spent this month yet.</p>`}
      </section>
      ${earned.length ? `<section class="card"><h2>Biggest earnings &amp; losses</h2><div class="rows">${earned.map((e) => row(e)).join("")}</div></section>` : ""}`;
  },

  list() {
    const { q, kind, cat, sort } = state.list;
    const needle = q.trim().toLowerCase();
    // A search looks through every month; otherwise only the selected one.
    let items = needle ? state.entries.filter((e) => `${e.name} ${e.category} ${e.note || ""}`.toLowerCase().includes(needle)) : inMonth(state.month);
    items = items.filter(shown);
    // Expenses paid by others are listed (struck through) but never added to a total.
    if (kind === "expense") items = items.filter((e) => e.kind === "expense");
    if (kind === "income") items = items.filter((e) => e.kind === "income");
    if (cat) items = items.filter((e) => e.category === cat);
    if (sort === "amount") items = [...items].sort((a, b) => b.amount - a.amount);
    const t = totals(items);
    const days = Map.groupBy ? Map.groupBy(items, (e) => e.date) : items.reduce((m, e) => m.set(e.date, [...(m.get(e.date) || []), e]), new Map());
    const chip = (k, txt) => `<button class="chip ${kind === k ? "on" : ""}" data-kind="${k}">${txt}</button>`;
    return `
      <div class="filters">
        <input id="q" type="search" placeholder="Search all months…" value="${esc(q)}" autocomplete="off">
        <div class="chips">${chip("all", "All")}${chip("expense", "Expenses")}${chip("income", "Income")}</div>
        <div class="filter-row">
          ${catPicker(kind, cat)}
          <div class="sortseg" role="group" aria-label="Sort by">
            <button type="button" data-sort="date" class="${sort === "date" ? "on" : ""}">Date</button>
            <button type="button" data-sort="amount" class="${sort === "amount" ? "on" : ""}">Amount</button>
          </div>
        </div>
      </div>
      <div class="days">
      <p class="summary">${items.length} movements${needle ? " (all months)" : ""} · ${
        kind === "expense" ? `total <b>${eur(t.spent)}</b>`
        : kind === "income" ? `total <b class="${t.income < 0 ? "neg" : "pos"}">${eur(t.income)}</b>`
        : `spent <b>${eur(t.spent)}</b> · income <b class="pos">${eur(t.income)}</b>`}</p>
      ${!items.length ? `<p class="empty">Nothing matches.</p>`
        : sort === "amount" ? `<div class="rows flat">${items.map((e) => row(e, true)).join("")}</div>`
        : [...days].map(([day, es]) => {
        const net = totals(es);
        const diff = net.income - net.spent;   // income and expenses on one day add up, with their sign
        const shownNet = net.spent || net.income ? `${diff < 0 ? "−" : "+"}${eur(Math.abs(diff))}` : "";
        return `<section class="day"><h3>${esc(dayName(day))}<span class="${diff > 0 ? "pos" : ""}">${shownNet}</span></h3>
          <div class="rows">${es.map((e) => row(e)).join("")}</div></section>`;
      }).join("")}
      </div>`;
  },

  // Stats cover the last 12 months, or one calendar year (the chips at the top).
  stats() {
    const period = state.period, keys = periodMonths(period), now = monthKey(new Date());
    const months = keys.map((key) => ({ key, ...totals(inMonth(key)) }));
    const active = months.filter((m) => m.spent || m.income);
    const n = active.length || 1;
    const sum = (f) => active.reduce((a, m) => a + m[f], 0);
    const range = state.entries.filter((e) => keys.includes(e.date.slice(0, 7)));
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
    const chip = (v, txt) => `<button class="chip ${period === v ? "on" : ""}" data-period="${v}">${txt}</button>`;
    return `
      <div class="period wide">${chip("12m", "Last 12 months")}${years().map((y) => chip(y, y)).join("")}</div>
      <p class="summary wide">${period === "12m" ? `${esc(monthName(keys[0]))} – ${esc(monthName(now))}` : `January – December ${period}`}</p>
      <section class="tiles wide">
        <div class="tile"><span>Spent / month</span><b>${eur0(sum("spent") / n)}</b></div>
        <div class="tile"><span>Income / month</span><b class="pos">${eur0(sum("income") / n)}</b></div>
        <div class="tile"><span>Savings rate</span><b>${sum("income") ? pct((sum("income") - sum("spent")) / sum("income")) : "—"}</b></div>
      </section>
      <section class="card wide"><h2>Income vs spent</h2>${monthChart(months)}</section>
      <section class="card"><h2>Average per month by category</h2>${catBars(byCat, byCat.reduce((a, [, v]) => a + v, 0))}</section>
      <section class="card"><h2>Where the money goes</h2>
        ${places.length ? `<ol class="places">${places.map((p) => `<li><span>${esc(emoji(p.cat))} ${esc(p.name)} <span class="muted">×${p.n}</span></span><b>${eur0(p.total)}</b></li>`).join("")}</ol>` : `<p class="empty">Nothing yet.</p>`}
      </section>
      <section class="card"><h2>Income sources</h2>${catBars(income, incomeTotal)}</section>`;
  },
};

function applyNav() {
  const nav = state.settings.nav || "top";
  document.documentElement.dataset.nav = nav;
  try { localStorage.setItem("mymoney.nav", nav); } catch {}
}

async function loadSettings() {
  try {
    state.settings = (await store.settings()).values;
    applyNav();
    render();
  } catch {}
}

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

  // Names typed before for this kind, most used first: shown as chips under the field, never as a dropdown.
  function names() {
    const n = new Map();
    for (const x of state.entries) if (x.kind === kind) n.set(x.name, (n.get(x.name) || 0) + 1);
    return [...n].sort((a, b) => b[1] - a[1]).map(([name]) => name);
  }
  const lastCat = (name) => state.entries.find((x) => x.kind === kind && x.name.toLowerCase() === name.trim().toLowerCase())?.category;

  function suggestions(typed) {
    const q = norm(typed);
    const all = names();
    // names that contain what you typed, or are one or two letters away from it (a typo of a name you already use)
    const hits = q ? all.filter((n) => norm(n) !== q && (norm(n).includes(q) || (q.length >= 4 && distance(norm(n), q) <= 2))) : all;
    return hits.slice(0, 8).map((n) => `<button type="button" data-name="${esc(n)}">${esc(n)}</button>`).join("");
  }
  const showCat = () => {
    const el = $(".cat-name", dlg);
    el.textContent = category ? label(category) : "Pick a category";
    el.classList.toggle("on", !!category);
  };

  function draw() {
    const url = store.receiptUrl(receipt);
    const attach = kind === "income" ? "Attach payslip, receipt or voucher" : "Add receipt photo";
    dlg.innerHTML = `<form method="dialog" class="sheet-body" novalidate>
      <div class="grab"></div>
      <div class="seg">
        <button type="button" data-k="expense" class="${kind === "expense" ? "on" : ""}">Expense</button>
        <button type="button" data-k="income" class="${kind === "income" ? "on" : ""}">Income</button>
      </div>
      <input class="amount" name="amount" inputmode="decimal" placeholder="0,00 €" value="${esc(e.amount)}" autocomplete="off" required>
      <input name="name" placeholder="${kind === "income" ? "From…" : "Where / what…"}" value="${esc(e.name)}"
        autocomplete="off" autocorrect="off" autocapitalize="sentences" spellcheck="false" enterkeyhint="done" required>
      <div class="sugg">${suggestions(e.name)}</div>
      <div class="cats">${categories(kind).map((c) => `<button type="button" class="cat ${c === category ? "on" : ""}" data-cat="${esc(c)}" title="${esc(label(c))}" aria-label="${esc(label(c))}" style="--c:${colorOf(c)}">${esc(emoji(c))}</button>`).join("")}</div>
      <div class="cat-name"></div>
      <div class="dates">
        <button type="button" data-day="0" class="${e.date === dayIso(0) ? "on" : ""}">Today</button>
        <button type="button" data-day="-1" class="${e.date === dayIso(-1) ? "on" : ""}">Yesterday</button>
        <button type="button" data-pick class="${e.date !== dayIso(0) && e.date !== dayIso(-1) ? "on" : ""}">📅 ${e.date !== dayIso(0) && e.date !== dayIso(-1) ? esc(dayName(e.date)) : "Pick a date"}</button>
        <input type="date" name="date" value="${esc(e.date)}" tabindex="-1" aria-hidden="true" required>
      </div>
      ${kind === "income"
        ? `<label class="gross">Gross (before tax)<input name="gross" inputmode="decimal" placeholder="optional" value="${esc(e.gross ?? "")}"></label>`
        : `<label class="toggle-pill"><input type="checkbox" name="paid_by_other" ${e.paid_by_other ? "checked" : ""}>Someone else paid</label>`}
      <input name="note" placeholder="Note (optional)" value="${esc(e.note ?? "")}">
      <label class="receipt">📎 ${receiptFile ? esc(receiptFile.name) : url ? `<a href="${url}" target="_blank">View file</a> · replace` : receipt ? "File kept in Google Drive · replace" : attach}
        <input type="file" name="receipt" accept="image/*,application/pdf" hidden></label>
      <p class="form-error" hidden></p>
      <div class="sheet-actions"></div>
    </form>`;
    showCat();
    actions(false);
  }

  // The bottom buttons; "Delete" swaps them for an inline question instead of a browser popup.
  function actions(confirming) {
    $(".sheet-actions", dlg).innerHTML = confirming
      ? `<p class="ask">Delete “${esc(e.name)}”?<small>This can't be undone.</small></p>
         <button type="button" class="pill" id="keep">Keep</button>
         <button type="button" class="pill solid-danger" id="del-yes">Delete</button>`
      : `${entry ? `<button type="button" class="pill danger" id="del">Delete</button>` : ""}
         <button type="button" class="pill" id="cancel">Cancel</button>
         <button type="submit" class="pill dark" id="save">${entry ? "Save" : "Add"}</button>`;
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
    } else if (btn.dataset.day != null || btn.dataset.pick != null) {
      const input = $("[name=date]", dlg);
      if (btn.dataset.pick != null) {
        try { input.showPicker(); } catch { input.focus(); input.click(); }
      } else {
        input.value = dayIso(Number(btn.dataset.day));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    } else if (btn.dataset.cat) {
      category = btn.dataset.cat; catTouched = true;
      dlg.querySelectorAll(".cat").forEach((b) => b.classList.toggle("on", b === btn));
      showCat();
    } else if (btn.dataset.name) {
      const input = $("[name=name]", dlg);
      input.value = btn.dataset.name;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (btn.id === "cancel") dlg.close();
    else if (btn.id === "del") actions(true);
    else if (btn.id === "keep") actions(false);
    else if (btn.id === "del-yes") {
      btn.disabled = true;
      try { await store.deleteEntry(e.id); dlg.close(); toast("Deleted"); await reload(); }
      catch (err) { toast(err.message, true); btn.disabled = false; }
    }
  };
  dlg.oninput = (ev) => {
    if (ev.target.name !== "name") return;
    $(".sugg", dlg).innerHTML = suggestions(ev.target.value);
    if (!catTouched) {
      const c = lastCat(ev.target.value);
      if (c) { category = c; dlg.querySelectorAll(".cat").forEach((b) => b.classList.toggle("on", b.dataset.cat === c)); showCat(); }
    }
  };
  dlg.onchange = (ev) => {
    if (ev.target.name === "date" && ev.target.value) { capture(); draw(); return; }
    if (ev.target.name === "receipt" && ev.target.files[0]) { capture(); receiptFile = ev.target.files[0]; draw(); }
  };
  dlg.onsubmit = async (ev) => {
    ev.preventDefault();
    capture();
    const err = $(".form-error", dlg);
    const amount = parseAmount(e.amount);
    const problem = !(kind === "income" ? amount : amount > 0) ? "Enter an amount (sums like 12,5+3 work; a negative income is a loss)"
      : !e.name.trim() ? "Enter a name" : !category ? "Pick a category" : !e.date ? "Pick a date" : null;
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    $("#save", dlg).disabled = true;
    try {
      if (receiptFile) receipt = await store.uploadReceipt(receiptFile);
      const gross = kind === "income" && e.gross ? parseAmount(e.gross) : null;
      // A new entry reuses the spelling you already have ("zara" -> "Zara"), so names don't drift apart
      const known = entry ? null : state.entries.find((x) => x.kind === kind && norm(x.name) === norm(e.name));
      await store.saveEntry({ id: entry?.id, kind, name: known ? known.name : e.name, category, date: e.date, amount, gross,
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

// ---------------------------------------------------------------- tidy names
// Settings > Tidy names: rename a name everywhere (typing one that exists merges them). Uses the same bottom sheet.
// Merging many spellings at once happens outside the app: ../tidy_names.py applies name_merges.json.
function openTidy(kind = "expense") {
  const dlg = $("#sheet");
  let renaming = null;   // a name being renamed, or null
  let q = "";

  function draw() {
    const all = nameList(kind);
    const needle = norm(q);
    const list = all.filter((x) => !needle || x.key.includes(needle)).sort((a, b) => a.name.localeCompare(b.name));
    dlg.innerHTML = `<div class="sheet-body tidy">
      <div class="grab"></div>
      <div class="seg">
        <button type="button" data-k="expense" class="${kind === "expense" ? "on" : ""}">Expenses</button>
        <button type="button" data-k="income" class="${kind === "income" ? "on" : ""}">Income</button>
      </div>
      ${renaming !== null ? `<div class="rename"><p><b>${esc(renaming)}</b> → <small>every entry with this name changes; if the new name exists, they merge</small></p>
          <input id="newname" value="${esc(renaming)}" autocomplete="off" autocapitalize="sentences" spellcheck="false">
          <div class="sheet-actions"><button type="button" class="pill" id="rn-cancel">Back</button><button type="button" class="pill dark" id="rn-save">Rename</button></div></div>` : `
      <h3>All names <small>${all.length}</small></h3>
      <input id="tq" type="search" placeholder="Search names…" value="${esc(q)}" autocomplete="off">
      <div class="all">${list.map((x) => `<button type="button" class="nm" data-rename="${esc(x.name)}">${esc(x.name)} <small>×${x.n}</small></button>`).join("") || `<p class="empty">No names.</p>`}</div>
      <p class="muted small">Tap a name to rename it. To merge many spellings at once, list them in name_merges.json and run tidy_names.py.</p>
      <div class="sheet-actions"><button type="button" class="pill dark" id="tidy-done">Done</button></div>`}
    </div>`;
  }

  async function apply(from, to) {
    try {
      const { renamed } = await store.renameNames(kind, from, to);
      toast(`${renamed} ${renamed === 1 ? "entry" : "entries"} renamed`);
      renaming = null;
      await reload();
      draw();
    } catch (err) { toast(err.message, true); }
  }

  dlg.onclick = (ev) => {
    if (ev.target === dlg) return dlg.close();
    const btn = ev.target.closest("button");
    if (!btn) return;
    const { k, rename } = btn.dataset;
    if (k) { kind = k; renaming = null; draw(); }
    else if (rename !== undefined) { renaming = rename; draw(); $("#newname", dlg).select(); }
    else if (btn.id === "rn-cancel") { renaming = null; draw(); }
    else if (btn.id === "rn-save") {
      const to = $("#newname", dlg).value.trim();
      if (to && to !== renaming) apply([renaming], to); else { renaming = null; draw(); }
    } else if (btn.id === "tidy-done") dlg.close();
  };
  dlg.oninput = (ev) => {
    if (ev.target.id !== "tq") return;
    q = ev.target.value;
    const pos = ev.target.selectionStart;
    draw();
    const el = $("#tq", dlg); el.focus(); el.setSelectionRange(pos, pos);
  };
  dlg.onchange = null;
  dlg.onsubmit = null;
  draw();
  dlg.showModal();
}

// ---------------------------------------------------------------- routing
function route() { return (location.hash.slice(1) || "home").split("?")[0]; }

function render() {
  const r = views[route()] ? route() : "home";
  $("#view").innerHTML = views[r]();
  $("#view").dataset.view = r;
  document.querySelectorAll("[data-tab]").forEach((a) => a.classList.toggle("active", a.dataset.tab === r));
  $("#month").hidden = r === "stats";
  $("#month-label").textContent = monthShort(state.month);
  drawMonthPop();
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
  const sortBtn = ev.target.closest("[data-sort]");
  if (sortBtn) { state.list.sort = sortBtn.dataset.sort; return render(); }
  if (ev.target.closest("#cat-btn")) { state.list.catOpen = !state.list.catOpen; return render(); }
  const opt = ev.target.closest(".catopt");
  if (opt) { state.list.cat = opt.dataset.cat; state.list.catOpen = false; return render(); }
  if (state.list.catOpen && !ev.target.closest(".catpick")) { state.list.catOpen = false; render(); }
  const chip = ev.target.closest(".chip");
  if (chip?.dataset.period) { state.period = chip.dataset.period; return render(); }
  if (chip) {
    state.list.kind = chip.dataset.kind;
    // keep the category only if it belongs to the new kind
    const ok = state.list.kind === "all" || categories(state.list.kind).includes(state.list.cat);
    if (!ok) state.list.cat = "";
    return render();
  }
  const bar = ev.target.closest(".mbar");
  if (bar) {
    state.month = bar.dataset.month;
    if (route() === "home") render(); else location.hash = "home";
    return;
  }
});
$("#view").addEventListener("input", (ev) => {
  if (ev.target.id !== "q") return;
  state.list.q = ev.target.value;
  const pos = ev.target.selectionStart;
  render();
  const q = $("#q"); q.focus(); q.setSelectionRange(pos, pos);
});

// App switcher menu (top left)
const appBtn = $(".app-btn"), appMenu = $(".app-menu");
const closeApps = () => { appMenu.hidden = true; appBtn.setAttribute("aria-expanded", "false"); };
appBtn.addEventListener("click", (ev) => {
  ev.stopPropagation();
  appMenu.hidden = !appMenu.hidden;
  appBtn.setAttribute("aria-expanded", String(!appMenu.hidden));
});
document.addEventListener("click", (ev) => { if (!ev.target.closest(".switcher")) closeApps(); });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeApps(); });
// Switching month slides the old page out and the new one in (dir 1: the new month comes from the right).
// The old page is a copy that stays on top until it has left; the real one is already the new month underneath.
function slideTo(key, dir) {
  if (key === state.month || key > monthKey(new Date())) return;
  const view = $("#view"), r = view.getBoundingClientRect();
  const ghost = view.cloneNode(true);
  ghost.removeAttribute("id");
  Object.assign(ghost.style, { position: "absolute", top: `${r.top + scrollY}px`, left: `${r.left + scrollX}px`,
    width: `${r.width}px`, margin: "0", pointerEvents: "none" });
  state.month = key;
  render();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  document.body.append(ghost);
  document.documentElement.classList.add("sliding");
  const opts = { duration: 280, easing: "cubic-bezier(.32,.72,.24,1)", fill: "both" };
  ghost.animate([{ transform: "none", opacity: 1 }, { transform: `translateX(${-dir * 35}%)`, opacity: 0 }], opts)
    .onfinish = () => { ghost.remove(); document.documentElement.classList.remove("sliding"); };
  view.animate([{ transform: `translateX(${dir * 35}%)`, opacity: 0 }, { transform: "none", opacity: 1 }], opts);
}
const stepMonth = (step) => slideTo(shiftMonth(state.month, step), step);

// Month picker: tap the month in the top bar, pick a year and a month. Months go up to the current one, never beyond.
const monthPop = { open: false, year: null };
function drawMonthPop() {
  $("#month-label").textContent = monthShort(state.month);
  const pop = $("#month-pop"), btn = $("#month-btn");
  pop.hidden = !monthPop.open;
  btn.setAttribute("aria-expanded", String(monthPop.open));
  if (!monthPop.open) return;
  const now = monthKey(new Date()), thisYear = Number(now.slice(0, 4));
  const first = Math.min(thisYear, ...state.entries.map((e) => Number(e.date.slice(0, 4))));
  const year = monthPop.year ?? Number(state.month.slice(0, 4));
  const has = new Set(state.entries.map((e) => e.date.slice(0, 7)));
  pop.innerHTML = `<div class="years">${Array.from({ length: thisYear - first + 1 }, (_, i) => thisYear - i).reverse()
      .map((y) => `<button type="button" data-year="${y}" class="${y === year ? "on" : ""}">${y}</button>`).join("")}</div>
    <div class="months">${Array.from({ length: 12 }, (_, i) => {
      const key = `${year}-${String(i + 1).padStart(2, "0")}`;
      return `<button type="button" data-m="${key}" class="${key === state.month ? "on" : ""} ${has.has(key) ? "has" : ""}" ${key > now ? "disabled" : ""}>${monthName(key, { month: "short" })}</button>`;
    }).join("")}</div>
    <button type="button" class="today" data-m="${now}" ${state.month === now ? "disabled" : ""}>This month</button>`;
  $(".years .on", pop)?.scrollIntoView({ inline: "center", block: "nearest" });   // a long list of years opens on the current one
  // Keep the popover on screen: it hangs from the button's right edge, so slide it back in if a narrow phone cuts it
  pop.style.transform = "";
  const r = pop.getBoundingClientRect(), edge = 12, vw = document.documentElement.clientWidth;
  const dx = r.left < edge ? edge - r.left : r.right > vw - edge ? vw - edge - r.right : 0;
  if (dx) pop.style.transform = `translateX(${dx}px)`;
}
function toggleMonthPop(open = !monthPop.open) {
  monthPop.open = open;
  monthPop.year = null;
  drawMonthPop();
}
$("#month-btn").addEventListener("click", (ev) => { ev.stopPropagation(); toggleMonthPop(); });
$("#month-pop").addEventListener("click", (ev) => {
  ev.stopPropagation();
  const b = ev.target.closest("button");
  if (!b) return;
  if (b.dataset.year) { monthPop.year = Number(b.dataset.year); drawMonthPop(); }
  else if (b.dataset.m) { toggleMonthPop(false); slideTo(b.dataset.m, b.dataset.m > state.month ? 1 : -1); }
});
document.addEventListener("click", () => { if (monthPop.open) toggleMonthPop(false); });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && monthPop.open) toggleMonthPop(false); });

// Swipe left / right on Home and Movements for the next / previous month.
let swipe = null;
document.addEventListener("touchstart", (ev) => {
  const ok = ev.touches.length === 1 && ["home", "list"].includes(route())
    && !ev.target.closest("dialog, .chips, .sugg, input, select, .app-menu");
  swipe = ok ? { x: ev.touches[0].clientX, y: ev.touches[0].clientY, t: Date.now() } : null;
}, { passive: true });
document.addEventListener("touchend", (ev) => {
  if (!swipe) return;
  const dx = ev.changedTouches[0].clientX - swipe.x, dy = ev.changedTouches[0].clientY - swipe.y;
  const quick = Date.now() - swipe.t < 700;
  swipe = null;
  if (quick && Math.abs(dx) > 70 && Math.abs(dx) > 2 * Math.abs(dy)) stepMonth(dx < 0 ? 1 : -1);
}, { passive: true });
$("#add-top").addEventListener("click", () => openSheet());

// Swipe the add sheet down to cancel it: drag from the top of the sheet (or anywhere while it is scrolled to the top).
(() => {
  const dlg = $("#sheet");
  let drag = null;
  dlg.addEventListener("touchstart", (ev) => {
    const t = ev.touches[0];
    drag = ev.touches.length === 1 && !ev.target.closest("input, textarea, .sugg, a")
      && (dlg.scrollTop <= 0 || ev.target.closest(".grab"))
      ? { y: t.clientY, x: t.clientX, dy: 0, on: false, t: Date.now() } : null;
  }, { passive: true });
  dlg.addEventListener("touchmove", (ev) => {
    if (!drag) return;
    const t = ev.touches[0], dy = t.clientY - drag.y;
    if (!drag.on) {
      if (dy < 8 || Math.abs(t.clientX - drag.x) > dy) { if (dy < -8) drag = null; return; }  // upwards or sideways: not a swipe down
      drag.on = true;
      dlg.style.transition = "none";
    }
    drag.dy = Math.max(0, dy);
    dlg.style.transform = `translateY(${drag.dy}px)`;
    ev.preventDefault();   // the sheet follows the finger instead of scrolling
  }, { passive: false });
  const end = () => {
    if (!drag?.on) { drag = null; return; }
    const fast = drag.dy / (Date.now() - drag.t) > 0.5;
    const close = drag.dy > 110 || (fast && drag.dy > 40);
    drag = null;
    dlg.style.transition = "transform .2s ease-out";
    dlg.style.transform = close ? "translateY(100%)" : "";
    setTimeout(() => { dlg.style.transition = ""; if (close) { dlg.close(); } dlg.style.transform = ""; }, 200);
  };
  dlg.addEventListener("touchend", end);
  dlg.addEventListener("touchcancel", end);
})();
// ⚙: the settings sheet shared with Portfolio (../../static/settings.js)
$("#open-settings").addEventListener("click", async () => {
  try {
    const { openSettings } = await import("/static/settings.js");
    openSettings({
      app: "gastos", accent: "var(--accent)",
      actions: [{ label: "Tidy names", help: "Fix a name everywhere, or merge it into another one", run: () => openTidy() }],
      onChange(name, value, values) {
        state.settings = values;
        if (name === "demo") return location.reload();
        if (name === "nav") applyNav();
        render();
      },
    });
  } catch (err) { toast(err.message, true); }
});
window.addEventListener("hashchange", () => { render(); scrollTo(0, 0); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
import("/static/settings.js").then((m) => m.reloadWhenDemoChanges()).catch(() => {});
loadSettings();
reload();
