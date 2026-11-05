// The settings sheet, shared by Gastos and Portfolio (both open it from the ⚙ in their top bar).
// What it shows comes from settings.py (/api/settings); the app you are in only decides which group comes first.
//
//     const { openSettings } = await import("/static/settings.js");
//     openSettings({ app: "gastos", accent: "var(--accent)", actions: [...], onChange(name, value, values) {...} })

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// Groups come in this order for each app; the rest follow in the order settings.py lists them.
const FIRST = { gastos: ["Gastos", "Look"], portfolio: ["Overview", "Returns", "Exposure", "Backtest", "Look"] };

// Forget everything kept on this phone (Gastos' entries, the portfolio pages): on sign-out.
export async function forgetLocal() {
  try { localStorage.removeItem("gastos.entries"); } catch {}
  try { await Promise.all((await caches.keys()).map((k) => caches.delete(k))); } catch {}
}

async function getJson(url, options) {
  const r = await fetch(url, options);
  if (r.status === 401) {
    await forgetLocal();
    location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    throw new Error("Signing in…");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `${r.status} ${r.statusText}`);
  return data;
}

function row(f, v) {
  const text = `<span>${esc(f.label)}${f.help ? `<small>${esc(f.help)}</small>` : ""}</span>`;
  const n = `data-setting="${esc(f.name)}"`;
  if (f.type === "toggle") return `<label class="st-row">${text}<span class="st-switch"><input type="checkbox" ${n} ${v ? "checked" : ""}><i></i></span></label>`;
  if (f.type === "select") return `<label class="st-row">${text}<select ${n}>${f.options.map((o) =>
    `<option value="${esc(o.value)}" ${o.value === String(v) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select></label>`;
  if (f.type === "number") return `<label class="st-row">${text}<input type="number" ${n} value="${esc(v)}" min="${f.min ?? ""}" max="${f.max ?? ""}" step="${f.step ?? 1}" inputmode="decimal"></label>`;
  return `<label class="st-row">${text}<input type="${esc(f.type)}" ${n} value="${esc(v)}"></label>`;
}

// Other tabs of the site (Gastos, Portfolio) hear about a setting that changes what they show: the demo switch.
const channel = "BroadcastChannel" in window ? new BroadcastChannel("mymoney-settings") : null;
export function reloadWhenDemoChanges() {
  if (channel) channel.onmessage = (ev) => { if (ev.data?.name === "demo") location.reload(); };
}

let dialog;
async function ready() {
  if (dialog) return dialog;
  const href = new URL("settings.css", import.meta.url).href;
  await new Promise((done) => {
    const link = Object.assign(document.createElement("link"), { rel: "stylesheet", href });
    link.onload = link.onerror = done;
    document.head.appendChild(link);
  });
  dialog = document.createElement("dialog");
  dialog.className = "st";
  document.body.appendChild(dialog);
  return dialog;
}

// actions: [{label, help, run}] extra rows under "Data" (Gastos adds "Tidy names").
export async function openSettings({ app, accent, actions = [], onChange = () => {} }) {
  const dlg = await ready();
  const [{ values, fields }, info] = await Promise.all([getJson("/api/settings"), getJson("/api/info").catch(() => ({}))]);
  const first = FIRST[app] || [];
  const rank = (g) => (first.includes(g) ? first.indexOf(g) : first.length);
  const groups = [...new Set(fields.map((f) => f.group))].sort((a, b) => rank(a) - rank(b));
  dlg.style.setProperty("--st-accent", accent || "var(--blue, #0666EB)");

  dlg.innerHTML = `<div class="st-body">
    <div class="st-head"><h2>Settings</h2><button type="button" class="st-x" aria-label="Close">✕</button></div>
    <section class="st-group"><h3>Account</h3><div class="st-list"><div class="st-row">
      <span>${info.email ? `Signed in as ${esc(info.email)}` : "Running on your computer"}<small>${info.email
        ? "Signing out also wipes the offline copy from this phone." : "No sign-in here."}</small></span>
      ${info.email ? `<a class="st-btn" href="/logout" data-out>Sign out</a>` : ""}</div></div></section>
    ${groups.map((g) => `<section class="st-group"><h3>${esc(g)}</h3><div class="st-list">
      ${fields.filter((f) => f.group === g).map((f) => row(f, values[f.name])).join("")}</div></section>`).join("")}
    <section class="st-group"><h3>Data</h3><div class="st-list">
      ${info.sheet ? `<a class="st-row st-link" href="${esc(info.sheet)}" target="_blank" rel="noopener"><span>Open the Google Sheet<small>Fix or sort rows there; keep the first row as it is. Changes show up within half a minute.</small></span>↗</a>` : ""}
      <a class="st-row st-link" href="/api/export.csv" download><span>Export movements as CSV</span>↓</a>
      ${actions.map((a, i) => `<button type="button" class="st-row st-link" data-action="${i}"><span>${esc(a.label)}${a.help ? `<small>${esc(a.help)}</small>` : ""}</span>›</button>`).join("")}
    </div></section>
    <p class="st-note">Saved for every device. Changes apply as soon as you make them.</p>
  </div>`;

  const note = dlg.querySelector(".st-note"), idle = note.textContent;
  dlg.onclick = async (ev) => {
    if (ev.target === dlg || ev.target.closest(".st-x")) return dlg.close();
    const out = ev.target.closest("[data-out]");
    if (out) { ev.preventDefault(); await forgetLocal(); location.href = "/logout"; return; }
    const action = ev.target.closest("[data-action]");
    if (action) { dlg.close(); actions[Number(action.dataset.action)].run(); }
  };
  dlg.onchange = async (ev) => {
    const name = ev.target.dataset.setting;
    if (!name) return;
    const value = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
    try {
      const saved = await getJson("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [name]: value }) });
      note.textContent = "Saved ✓"; note.classList.remove("bad");
      if (name === "demo") await forgetLocal();  // the offline copy of the entries would show the other kind of data
      channel?.postMessage({ name, value });
      onChange(name, value, saved);
    } catch (err) {
      note.textContent = err.message; note.classList.add("bad");
    }
    setTimeout(() => { note.textContent = idle; note.classList.remove("bad"); }, 1800);
  };
  dlg.showModal();
}
