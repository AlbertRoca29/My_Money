// Gastos — the screens. Data comes from store.js; this file only filters, sums and draws.
import * as store from "./store.js";
import { sticker } from "./stickers.js";

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
  period: null,                  // Stats: "12m" (last 12 months) or a year, "2025"; null = Settings > Stats open on
  statCat: "",                   // Stats: the category drawn month by month (click one in "Average per month")
  jumpTo: null,                  // after switching view, scroll to (and flash) this element id
  settings: {},                  // ../../settings.py values (hide_others, top_min, budget…)
};

// ---------------------------------------------------------------- helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const eurFmt = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });
const eur0Fmt = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const eur = (n) => eurFmt.format(n);
const eur0 = (n) => eur0Fmt.format(n);
const pct = (n) => `${Math.round(n * 100)}%`;
// Phones (and narrow windows): tabs at the bottom, charts drawn at the card's real width so their labels stay readable.
const PHONE = matchMedia("(max-width: 899px)");
// A card's inner width there: <main> is at most 640px wide with 16px padding each side, a card has 18px.
const cardWidth = () => Math.max(260, Math.min(document.documentElement.clientWidth, 640) - 32 - 36);

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
// The drawing for a category (its sticker), or its emoji when it has none.
const glyph = (cat) => sticker(label(cat)) || esc(emoji(cat));
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
// withCat: the category's name under the movement's (Movements leaves it out: the sticker already says it).
function row(e, withDate = false, withCat = true) {
  const loss = e.kind === "income" && e.amount < 0;   // a negative income is a loss
  const sign = e.kind === "income" ? (loss ? "−" : "+") : "−";
  const cls = loss ? "neg" : e.kind === "income" ? "pos" : counts(e) ? "" : "other";
  return `<button class="row" data-id="${esc(e.id)}">
    <span class="avatar" style="--c:${colorOf(e.category)}">${glyph(e.category)}</span>
    <span class="row-main">
      <span class="row-name">${esc(e.name)}${e.receipt ? ' <span class="clip" title="Has receipt">📎</span>' : ""}</span>
      <span class="row-sub">${[withCat && label(e.category), withDate && dayName(e.date)].filter(Boolean).map(esc).join(" · ")}</span>
    </span>
    <span class="row-amt ${cls}">${sign}${eur(Math.abs(e.amount))}</span>
  </button>`;
}

function catBars(pairs, total, pick = false) {
  if (!pairs.length) return `<p class="empty">Nothing yet.</p>`;
  const max = pairs[0][1];
  return `<div class="bars">${pairs.map(([cat, v]) => `
    <div class="bar-row ${pick ? "pick" : ""} ${pick && state.statCat === cat ? "on" : ""}" ${pick ? `data-statcat="${esc(cat)}" ${tipAttr(label(cat), `${eur(v)} a month`, `${pct(v / total)} of the total`, state.statCat === cat ? "Click again to close" : "Click to see it month by month")}` : ""}>
      <span class="bar-label">${glyph(cat)} ${esc(label(cat))}</span>
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
  const phone = PHONE.matches, H = 170, pad = { t: 10, b: 24, l: 26 };
  const slot = phone ? (cardWidth() - pad.l) / months.length : 30, bw = phone ? Math.min(9, slot * 0.32) : 9;
  const W = pad.l + slot * months.length;
  const ticks = niceTicks(Math.max(...months.flatMap((m) => [m.income, m.spent])));
  const max = ticks.at(-1);
  const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const now = monthKey(new Date());
  const grid = ticks.map((v) => `<line x1="${pad.l}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/>
    <text x="${pad.l - 5}" y="${y(v) + 3}" text-anchor="end">${compact(v)}</text>`).join("");
  const bars = months.map((m, i) => {
    const x = pad.l + i * slot + slot / 2;
    return `<g class="mbar" data-month="${m.key}" ${tipAttr(monthName(m.key), `Income ${eur0(m.income)}`, `Spent ${eur0(m.spent)}`, `Saved ${eur0(m.income - m.spent)}`, phone ? "Tap again to open the month" : "Click to open the month")}>
      <rect class="hit" x="${x - slot / 2}" y="0" width="${slot}" height="${H}" rx="6" fill="transparent"/>
      <rect x="${x - bw - 1}" y="${y(m.income)}" width="${bw}" height="${H - pad.b - y(m.income)}" rx="2" fill="var(--pos)"/>
      <rect x="${x + 1}" y="${y(m.spent)}" width="${bw}" height="${H - pad.b - y(m.spent)}" rx="2" fill="var(--neg)"/>
      <text x="${x}" y="${H - 6}" text-anchor="middle" class="m ${m.key === now ? "cur" : ""}">${monthName(m.key, { month: "narrow" })}</text>
    </g>`;
  }).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Income and spending per month">
    ${grid}${bars}</svg>
    <div class="legend"><span><i style="background:var(--pos)"></i>Income</span><span><i style="background:var(--neg)"></i>Spent</span><span class="muted">${phone ? "Tap a month for details" : "Click a month to open it"}</span></div>`;
}

// The month's spending as one stacked bar, then the biggest categories (the rest summed as "Other").
function catStack(pairs, total) {
  if (!pairs.length) return `<p class="empty">Nothing spent yet.</p>`;
  const top = pairs.slice(0, 5), rest = pairs.slice(5).reduce((a, [, v]) => a + v, 0);
  const parts = [...top.map(([c, v]) => [label(c), v, colorOf(c), c]), ...(rest ? [["Other", rest, "#C9CED4", ""]] : [])];
  const go = (cat, n, v) => (cat ? `data-cat="${esc(cat)}" ${tipAttr(n, `${eur(v)} · ${pct(v / total)}`, "Click to see these movements")}` : tipAttr(n, `${eur(v)} · ${pct(v / total)}`));
  return `<div class="stack">${parts.map(([n, v, c, cat]) => `<i style="flex:${v};background:${c}" ${go(cat, n, v)}></i>`).join("")}</div>
    <div class="legend-list">${parts.map(([n, v, c, cat]) => `<div class="${cat ? "go" : ""}" ${go(cat, n, v)}><i style="background:${c}"></i><span>${esc(n)}</span><b>${eur0(v)}</b><em>${pct(v / total)}</em></div>`).join("")}</div>`;
}

// ---------------------------------------------------------------- desktop charts (hover shows #tip, clicks drill in)
const daysIn = (key) => new Date(+key.slice(0, 4), +key.slice(5, 7), 0).getDate();
const spentOf = (es) => es.filter((e) => e.kind === "expense" && counts(e));
// Spending per day of a month: index 1..days (0 stays empty).
function dailySpent(key) {
  const a = Array(daysIn(key) + 1).fill(0);
  for (const e of spentOf(inMonth(key))) a[+e.date.slice(8)] += e.amount;
  return a;
}
const running = (a) => { let s = 0; return a.map((v, i) => (i ? (s += v) : 0)); };
const tipAttr = (...lines) => `data-tip="${esc(lines.filter(Boolean).join("\n"))}"`;

// The month as a calendar: darker squares for bigger days. A day with movements opens them; an empty one adds one.
function calendar(key) {
  const per = dailySpent(key), days = per.length - 1, today = todayIso();
  const ws = state.settings.week_start === "sun" ? 0 : 1;
  const offset = (new Date(+key.slice(0, 4), +key.slice(5, 7) - 1, 1).getDay() - ws + 7) % 7;
  const names = (ws ? ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
    .map((n) => (PHONE.matches ? n[0] : n));
  const max = Math.max(...per, 1);
  const cells = Array.from({ length: days }, (_, i) => {
    const d = i + 1, iso = `${key}-${String(d).padStart(2, "0")}`, v = per[d], n = inMonth(key).filter((e) => e.date === iso && shown(e)).length;
    const a = v ? 0.12 + 0.78 * Math.sqrt(v / max) : 0;
    return `<button type="button" class="cal-day ${iso === today ? "today" : ""} ${a > 0.6 ? "dark" : ""}" data-day="${iso}" ${iso > today ? "disabled" : ""}
      style="--a:${a.toFixed(3)}" ${tipAttr(dayName(iso), v ? `Spent ${eur(v)}` : "Nothing spent", n ? `${n} movement${n > 1 ? "s" : ""} · click to see` : iso <= today ? "Click to add one" : "")}>
      <span>${d}</span>${v ? `<b>${compact(Math.round(v))}</b>` : ""}</button>`;
  }).join("");
  const spentDays = per.filter((v) => v > 0).length, elapsed = key === today.slice(0, 7) ? +today.slice(8) : days;
  return `<div class="cal">${names.map((n) => `<span class="cal-h">${n}</span>`).join("")}${'<span></span>'.repeat(offset)}${cells}</div>
    <div class="legend"><span>${spentDays} of ${elapsed} days with spending</span>
      <span class="cal-scale">Less <i style="--a:.15"></i><i style="--a:.4"></i><i style="--a:.65"></i><i style="--a:.9"></i> More</span></div>`;
}

// Saved per month (income − spent) as bars above / below zero, with the running total as a line.
// On a phone it is drawn at the card's real width (labels keep their size), one letter per month, and the running
// total's scale moves into the legend so the bars get the room.
function savedChart(months) {
  const phone = PHONE.matches, H = phone ? 180 : 200;
  const pad = phone ? { t: 12, b: 22, l: 32, r: 6 } : { t: 14, b: 24, l: 40, r: 44 };
  const slot = phone ? (cardWidth() - pad.l - pad.r) / months.length : 44, bw = phone ? Math.min(16, slot * 0.55) : 18;
  const W = pad.l + slot * months.length + pad.r;
  const vals = months.map((m) => m.income - m.spent), cum = running([0, ...vals]).slice(1);
  // bars on the left scale, the running total on its own (right) scale, so neither squashes the other
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals, 100);
  const span = hi - lo || 1, y = (v) => pad.t + (H - pad.t - pad.b) * ((hi - v) / span);
  const clo = Math.min(0, ...cum), chi = Math.max(...cum, 1);
  const yc = (v) => pad.t + (H - pad.t - pad.b) * ((chi - v) / (chi - clo || 1));
  const cx = (i) => pad.l + i * slot + slot / 2;
  const now = monthKey(new Date());
  const bars = months.map((m, i) => {
    const v = vals[i];
    return `<g class="mbar" data-month="${m.key}" ${tipAttr(monthName(m.key), `Saved ${eur0(v)}`, m.income ? `Savings rate ${pct(v / m.income)}` : "", `Running total ${eur0(cum[i])}`, phone ? "Tap again to open the month" : "Click to open the month")}>
      <rect class="hit" x="${cx(i) - slot / 2}" y="0" width="${slot}" height="${H}" rx="6" fill="transparent"/>
      <rect x="${cx(i) - bw / 2}" y="${Math.min(y(v), y(0))}" width="${bw}" height="${Math.max(1, Math.abs(y(v) - y(0)))}" rx="3" fill="${v >= 0 ? "var(--pos)" : "var(--neg)"}"/>
      <text x="${cx(i)}" y="${H - 6}" text-anchor="middle" class="m ${m.key === now ? "cur" : ""}">${monthName(m.key, { month: phone ? "narrow" : "short" })}</text></g>`;
  }).join("");
  const path = cum.map((v, i) => `${i ? "L" : "M"}${cx(i).toFixed(1)},${yc(v).toFixed(1)}`).join("");
  return `<svg class="chart wide-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Saved per month">
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink-2)" stroke-opacity=".35"/>
      ${y(0) - y(hi) > 12 ? `<text x="${pad.l - 6}" y="${y(hi) + 3}" text-anchor="end">${compact(Math.round(hi))}</text>` : ""}
      <text x="${pad.l - 6}" y="${y(0) + 3}" text-anchor="end">0</text>
      ${lo < 0 && y(lo) - y(0) > 12 ? `<text x="${pad.l - 6}" y="${y(lo) + 3}" text-anchor="end">−${compact(Math.round(-lo))}</text>` : ""}
      ${phone ? "" : `<text x="${W - pad.r + 6}" y="${yc(chi) + 3}" class="cum-txt">${compact(Math.round(chi))}</text>
      ${clo < 0 ? `<text x="${W - pad.r + 6}" y="${yc(clo) + 3}" class="cum-txt">−${compact(Math.round(-clo))}</text>` : ""}`}
      ${bars}<path d="${path}" class="cum-line"/>${cum.map((v, i) => `<circle cx="${cx(i).toFixed(1)}" cy="${yc(v).toFixed(1)}" r="${phone ? 2.5 : 3}" class="cum-dot"/>`).join("")}
    </svg>
    <div class="legend"><span><i style="background:var(--pos)"></i>Saved</span><span><i style="background:var(--neg)"></i>Overspent</span>
      <span><i style="background:var(--ink)"></i>${phone ? `Running total <b>${eur0(cum.at(-1))}</b>` : "Running total (right scale)"}</span></div>`;
}

// One category month by month (the bar picked in "Average per month by category").
function categoryChart(cat, keys) {
  const vals = keys.map((k) => inMonth(k).filter((e) => e.category === cat && (e.kind === "income" || counts(e))).reduce((a, e) => a + e.amount, 0));
  const max = Math.max(...vals, 1), active = vals.filter((v) => v), avg = active.length ? active.reduce((a, b) => a + b, 0) / active.length : 0;
  const c = colorOf(cat);
  return `<div class="cm">${keys.map((k, i) => `<button type="button" class="cm-col mbar-btn" data-month="${k}" ${tipAttr(monthName(k), eur(vals[i]), avg && vals[i] ? `${vals[i] > avg ? "+" : "−"}${pct(Math.abs(vals[i] - avg) / avg)} vs its average` : "", "Click to open the month")}>
      <span class="cm-bar"><i style="height:${(vals[i] / max) * 100}%;background:${c}"></i></span><em>${monthName(k, { month: "narrow" })}</em></button>`).join("")}
      ${avg ? `<span class="cm-avg" style="bottom:calc(22px + ${(avg / max) * 130}px)"><span>avg ${eur0(avg)}</span></span>` : ""}</div>`;
}

// Settings > Gastos > Monthly budget: how much of it is gone, where you'd be at an even pace, what's left per day.
function budgetBar(spent, upTo) {
  const budget = Number(state.settings.budget) || 0;
  if (!budget) return "";
  const days = daysIn(state.month), isNow = upTo !== "31", left = budget - spent;
  const even = isNow ? Number(upTo) / days : 1, daysLeft = days - Number(upTo) + 1;
  const over = spent > budget, ahead = spent > budget * even;
  return `<div class="budget ${over ? "over" : ahead ? "ahead" : ""}" ${tipAttr(`Budget ${eur(budget)}`, `Spent ${eur(spent)} (${pct(spent / budget)})`,
      isNow ? `An even pace would be ${eur0(budget * even)} by today` : "")}>
    <div class="budget-top"><span>${over ? `<b>${eur0(-left)}</b> over the ${eur0(budget)} budget` : `<b>${eur0(left)}</b> left of ${eur0(budget)}`}</span>
      ${isNow && !over ? `<span class="muted">${eur0(left / daysLeft)}/day for ${daysLeft} more day${daysLeft > 1 ? "s" : ""}</span>` : ""}</div>
    <div class="budget-track"><i style="width:${Math.min(100, (spent / budget) * 100)}%"></i>${isNow ? `<em style="left:${even * 100}%"></em>` : ""}</div>
  </div>`;
}

// Go to a view (or stay) and bring one element of it into sight, flashing it.
function jump(view, id) {
  state.jumpTo = id;
  if (route() === view) { render(); afterRender(); } else location.hash = view;
}
function afterRender() {
  const id = state.jumpTo;
  state.jumpTo = null;
  const el = id && document.getElementById(id);
  if (!el) return scrollTo(0, 0);
  el.scrollIntoView({ block: "center", behavior: state.settings.motion === false ? "auto" : "smooth" });
  el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
}

// The floating tooltip used by every chart above (and anything else with data-tip). With a mouse it follows the
// pointer; on a touch screen it shows above the finger, centred on it, so the finger doesn't hide it.
let touching = false;   // the last pointer was a finger
function showTip(ev, text) {
  const tip = $("#tip");
  if (tip.hidden || tip.textContent !== text) { tip.textContent = text; tip.hidden = false; }
  const r = tip.getBoundingClientRect(), vw = document.documentElement.clientWidth, edge = 8;
  let left, top;
  if (touching) {
    left = Math.max(edge, Math.min(vw - r.width - edge, ev.clientX - r.width / 2));
    top = ev.clientY - r.height - 22;
    if (top < edge) top = ev.clientY + 26;
  } else {
    left = ev.clientX + 14; top = ev.clientY + 16;
    if (left + r.width > vw - edge) left = ev.clientX - r.width - 14;
    if (top + r.height > innerHeight - edge) top = ev.clientY - r.height - 12;
  }
  tip.style.transform = `translate(${left}px, ${top}px)`;
}
const hideTip = () => {
  const t = $("#tip");
  if (t) t.hidden = true;
  document.querySelectorAll(".mbar.on, .mbar-btn.on").forEach((b) => b.classList.remove("on"));
};
document.addEventListener("pointerdown", (ev) => { touching = ev.pointerType !== "mouse"; }, { capture: true, passive: true });
document.addEventListener("pointermove", (ev) => { if (ev.pointerType === "mouse") touching = false; }, { passive: true });
document.addEventListener("mousemove", (ev) => {
  if (touching) return;   // a tap also sends a mousemove: on touch the click handler below decides
  const el = ev.target.closest?.("[data-tip]");
  if (el) showTip(ev, el.dataset.tip); else hideTip();
});
document.addEventListener("mouseleave", hideTip);
addEventListener("scroll", () => { if (touching) hideTip(); }, { passive: true });
// Touch: the first tap on a chart bar only shows its numbers; a second tap on the same bar opens it.
// Returns true when the tap was used for that.
function touchTip(ev) {
  if (!touching) return false;
  const el = ev.target.closest("[data-tip]"), bar = el?.closest(".mbar, .mbar-btn");
  const first = bar && !bar.classList.contains("on");
  hideTip();
  if (first) { showTip(ev, el.dataset.tip); bar.classList.add("on"); return true; }
  // something that only informs (no action of its own): the tap shows its numbers
  if (el && !bar && !el.matches("button, a, .go, [data-cat], [data-q], [data-statcat]")) { showTip(ev, el.dataset.tip); return true; }
  return false;   // anything else acts at once, with no tooltip left behind
}
document.addEventListener("click", (ev) => { if (touching && !ev.target.closest("#view [data-tip]")) hideTip(); });

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

// Movements' category filter: a button that opens a menu (a native <select> looks different in every browser).
function catPicker(kind, cat) {
  const item = (value, c, text) => `<button type="button" class="catopt ${value === cat ? "on" : ""}" data-cat="${esc(value)}">
    <span class="avatar sm" style="--c:${c ? colorOf(c) : "var(--ink-2)"}">${c ? glyph(c) : "✦"}</span><span>${esc(text)}</span>
    ${value === cat ? '<svg class="tick"><use href="#i-check"/></svg>' : ""}</button>`;
  const group = (k, title) => `${title ? `<div class="cathead">${title}</div>` : ""}${categories(k).map((c) => item(c, c, label(c))).join("")}`;
  const all = kind === "income" ? "All income" : kind === "expense" ? "All expenses" : "All categories";
  const menu = kind === "all" ? group("expense", "Expenses") + group("income", "Income") : group(kind);
  return `<div class="catpick">
    <button type="button" class="catbtn ${cat ? "set" : ""}" id="cat-btn" aria-haspopup="listbox" aria-expanded="${state.list.catOpen}">
      ${cat ? `<span class="avatar sm" style="--c:${colorOf(cat)}">${glyph(cat)}</span><span>${esc(label(cat))}</span>` : `<span>${all}</span>`}
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
          <div><span>Movements</span><b>${month.filter(shown).length}</b></div>
          ${t.spent ? `<div><span>Per day</span><b>${eur0(t.spent / (upTo === "31" ? daysIn(state.month) : Number(upTo)))}</b></div>` : ""}
        </div>
        ${budgetBar(t.spent, upTo)}
      </div>
      <section class="card"><h2>Where it went</h2>${catStack(byCat, t.spent)}</section>
      <section class="card">
        <h2>Biggest expenses <a href="#list" class="link">See all</a></h2>
        ${top.length ? `<div class="rows">${top.map((e) => row(e)).join("")}</div>` : `<p class="empty">Nothing spent this month yet.</p>`}
      </section>
      ${state.settings.calendar === false ? "" : `<section class="card"><h2>Calendar <span class="h-sub">${PHONE.matches ? "Tap" : "Click"} a day</span></h2>${calendar(state.month)}</section>`}
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
        // One flat list, newest first (or biggest): the sticker says the category, the row says the day.
        : `<div class="rows flat">${items.map((e) => row(e, true, false)).join("")}</div>`}
      </div>`;
  },

  // Stats cover the last 12 months, or one calendar year (the chips at the top).
  stats() {
    const period = state.period ??= state.settings.stats_period === "year" ? String(new Date().getFullYear()) : "12m";
    const keys = periodMonths(period), now = monthKey(new Date());
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
    const best = active.filter((m) => m.key !== now && m.spent > 0).sort((a, b) => a.spent - b.spent)[0];
    return `
      <div class="period wide">${chip("12m", "Last 12 months")}${years().map((y) => chip(y, y)).join("")}</div>
      <p class="summary wide">${period === "12m" ? `${esc(monthName(keys[0]))} – ${esc(monthName(now))}` : `January – December ${period}`}</p>
      <section class="tiles wide">
        <div class="tile"><span>Spent / month</span><b>${eur0(sum("spent") / n)}</b></div>
        <div class="tile"><span>Income / month</span><b class="pos">${eur0(sum("income") / n)}</b></div>
        <div class="tile"><span>Saved / month</span><b class="${sum("income") - sum("spent") < 0 ? "neg" : ""}">${eur0((sum("income") - sum("spent")) / n)}</b></div>
        <div class="tile"><span>Savings rate</span><b>${sum("income") ? pct((sum("income") - sum("spent")) / sum("income")) : "—"}</b></div>
        ${best ? `<div class="tile go" data-month="${best.key}" ${tipAttr("Click to open it")}><span>Cheapest month</span><b>${esc(monthName(best.key, { month: "short" }))} · ${eur0(best.spent)}</b></div>` : ""}
      </section>
      <section class="card wide"><h2>Income vs spent</h2>${monthChart(months)}</section>
      <section class="card wide"><h2>Saved per month <span class="h-sub">Income minus spending, and the running total</span></h2>${savedChart(months)}</section>
      <section class="card"><h2>Average per month by category <span class="h-sub">${PHONE.matches ? "Tap" : "Click"} one</span></h2>${catBars(byCat, byCat.reduce((a, [, v]) => a + v, 0), true)}</section>
      ${state.statCat ? `<section class="card" id="statcat"><h2><span class="h-title"><span class="h-ico">${glyph(state.statCat)}</span>${esc(label(state.statCat))}</span><span class="h-sub">Month by month</span><button type="button" class="x-btn" data-statcat="${esc(state.statCat)}" aria-label="Close">✕</button></h2>${categoryChart(state.statCat, keys)}
        <p class="see"><button type="button" class="link" data-cat="${esc(state.statCat)}">See every movement →</button></p></section>` : ""}
      <section class="card"><h2>Where the money goes <span class="h-sub">${PHONE.matches ? "Tap" : "Click"} a name</span></h2>
        ${places.length ? `<ol class="places">${places.map((p) => `<li data-q="${esc(p.name)}" ${tipAttr(p.name, `${eur(p.total)} in ${p.n} movement${p.n > 1 ? "s" : ""}`, `${eur(p.total / p.n)} each on average`, "Click to search for it")}><span>${glyph(p.cat)} ${esc(p.name)} <span class="muted">×${p.n}</span></span><b>${eur0(p.total)}</b></li>`).join("")}</ol>` : `<p class="empty">Nothing yet.</p>`}
      </section>
      <section class="card"><h2>Income sources</h2>${catBars(income, incomeTotal)}</section>`;
  },
};

// Settings > Look: hide amounts, animations.
function applyLook() {
  const d = document.documentElement.dataset;
  d.privacy = state.settings.privacy ? "on" : "off";
  d.motion = state.settings.motion === false ? "off" : "on";
}

async function loadSettings() {
  try {
    state.settings = (await store.settings()).values;
    applyLook();
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

function openSheet(entry = null, defaults = {}) {
  const e = entry || { kind: "expense", name: "", category: "", date: todayIso(), amount: "", gross: "", paid_by_other: false, note: "", ...defaults };
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
      <div class="cats">${categories(kind).map((c) => `<button type="button" class="cat ${c === category ? "on" : ""}" data-cat="${esc(c)}" title="${esc(label(c))}" aria-label="${esc(label(c))}" style="--c:${colorOf(c)}">${glyph(c)}</button>`).join("")}</div>
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
  const view = $("#view"), fresh = view.dataset.view !== r;
  view.innerHTML = views[r]();
  view.dataset.view = r;
  if (fresh) { view.classList.add("enter"); clearTimeout(render.t); render.t = setTimeout(() => view.classList.remove("enter"), 700); }   // cards fade in on a new view only
  document.querySelectorAll("[data-tab]").forEach((a) => a.classList.toggle("active", a.dataset.tab === r));
  $("#month").hidden = r === "stats";
  $("#month-label").textContent = monthShort(state.month);
  drawMonthPop();
}

async function reload() {
  const early = store.cachedEntries();   // draw the last list at once; the server may still be waking up
  if (early && !state.entries?.length) { state.entries = early; render(); }
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
  if (touchTip(ev)) return;
  // Calendar: a day with movements shows them in Movements; an empty day opens a new one on that date.
  const calDay = ev.target.closest(".cal-day");
  if (calDay) {
    const iso = calDay.dataset.day;
    if (state.entries.some((e) => e.date === iso && shown(e))) {
      Object.assign(state.list, { q: "", kind: "all", cat: "", sort: "date", catOpen: false });
      return jump("list", `d-${iso}`);
    }
    return openSheet(null, { date: iso });
  }
  // A category (Home's "Where it went", Stats' "See every movement"): Movements filtered to it.
  const goCat = ev.target.closest("[data-cat]:not(.catopt)");
  if (goCat) {
    const cat = goCat.dataset.cat, kind = categories("income").includes(cat) && !categories("expense").includes(cat) ? "income" : "expense";
    // from Stats every month counts, so search by its name too (a search looks through all months)
    Object.assign(state.list, { q: route() === "stats" ? label(cat) : "", kind, cat, sort: "date", catOpen: false });
    return jump("list", null);
  }
  const statCat = ev.target.closest("[data-statcat]");
  if (statCat) {
    state.statCat = state.statCat === statCat.dataset.statcat ? "" : statCat.dataset.statcat;
    return state.statCat ? jump("stats", "statcat") : render();
  }
  const place = ev.target.closest("[data-q]");
  if (place) {
    Object.assign(state.list, { q: place.dataset.q, kind: "expense", cat: "", sort: "date", catOpen: false });
    return jump("list", null);
  }
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
  const bar = ev.target.closest(".mbar, .mbar-btn, .tile.go");
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
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || state.settings.motion === false) return;
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
  // Keep the popover on screen: it hangs from the button's right edge, so slide it back in if the window cuts it
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
  const ok = ev.touches.length === 1 && ["home", "list"].includes(route()) && !$("dialog[open]")
    && !ev.target.closest(".chips, .sugg, input, select, .app-menu, .month-pop, .catmenu, .tabbar, .topbar");
  swipe = ok ? { x: ev.touches[0].clientX, y: ev.touches[0].clientY, t: Date.now() } : null;
}, { passive: true });
document.addEventListener("touchend", (ev) => {
  if (!swipe) return;
  const dx = ev.changedTouches[0].clientX - swipe.x, dy = ev.changedTouches[0].clientY - swipe.y;
  const quick = Date.now() - swipe.t < 700;
  swipe = null;
  if (quick && Math.abs(dx) > 70 && Math.abs(dx) > 2 * Math.abs(dy)) { hideTip(); stepMonth(dx < 0 ? 1 : -1); }
}, { passive: true });
document.addEventListener("touchcancel", () => { swipe = null; }, { passive: true });

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
    setTimeout(() => { dlg.style.transition = ""; if (close) dlg.close(); dlg.style.transform = ""; }, 200);
  };
  dlg.addEventListener("touchend", end);
  dlg.addEventListener("touchcancel", end);
})();

// Crossing the phone / desktop width, or turning the phone, redraws the charts at the new width.
PHONE.addEventListener("change", () => { hideTip(); render(); });
let lastWidth = document.documentElement.clientWidth;
addEventListener("resize", () => {
  const w = document.documentElement.clientWidth;
  if (!PHONE.matches || Math.abs(w - lastWidth) < 24) return;   // a phone's toolbar sliding in changes only the height
  lastWidth = w;
  clearTimeout(render.resize);
  render.resize = setTimeout(render, 150);
});

$("#add-top").addEventListener("click", () => openSheet());

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
        if (name === "stats_period") state.period = null;
        applyLook();
        render();
      },
    });
  } catch (err) { toast(err.message, true); }
});
window.addEventListener("hashchange", () => { hideTip(); render(); afterRender(); });

// ---------------------------------------------------------------- keyboard (desktop)
// ← → months · 1 2 3 views · N new movement · / search · H hide amounts · , settings
document.addEventListener("keydown", (ev) => {
  if (ev.metaKey || ev.ctrlKey || ev.altKey || ev.target.closest("input, textarea, select, dialog") || $("dialog[open]")) return;
  const k = ev.key.toLowerCase();
  if (k === "arrowleft" || k === "arrowright") { if (route() !== "stats") stepMonth(k === "arrowright" ? 1 : -1); }
  else if (["1", "2", "3"].includes(k)) location.hash = ["home", "list", "stats"][+k - 1];
  else if (k === "n") openSheet();
  else if (k === "/") { ev.preventDefault(); if (route() !== "list") location.hash = "list"; setTimeout(() => $("#q")?.focus(), 30); }
  else if (k === "h") { const d = document.documentElement.dataset; d.privacy = d.privacy === "on" ? "off" : "on"; }
  else if (k === ",") $("#open-settings").click();
  else return;
  ev.preventDefault();
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
import("/static/settings.js").then((m) => m.reloadWhenDemoChanges()).catch(() => {});
loadSettings();
reload();
