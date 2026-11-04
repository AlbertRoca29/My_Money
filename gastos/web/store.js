// The only file that knows where the data lives. Today: the Flask API in server.py.
// To move to GitHub Pages + a hosted database (Supabase, Firebase…), rewrite these functions with the
// same names and return shapes; nothing else in web/ needs to change.

const CACHE_KEY = "gastos.entries";

async function call(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    body: body instanceof FormData ? body : body && JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

// Every entry, newest first. Falls back to the last copy seen when offline.
export async function listEntries() {
  try {
    const entries = await call("GET", "api/entries");
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(entries)); } catch {}
    return { entries, offline: false };
  } catch (err) {
    let cached = null;
    try { cached = JSON.parse(localStorage.getItem(CACHE_KEY)); } catch {}
    if (cached) return { entries: cached, offline: true };
    throw err;
  }
}

export const saveEntry = (entry) =>
  entry.id ? call("PUT", `api/entries/${entry.id}`, entry) : call("POST", "api/entries", entry);

export const deleteEntry = (id) => call("DELETE", `api/entries/${id}`);

// Upload a receipt photo/PDF; resolves to the name to store in entry.receipt.
export async function uploadReceipt(file) {
  const form = new FormData();
  form.append("file", file);
  return (await call("POST", "api/receipts", form)).receipt;
}

// A URL to show a stored receipt, or null for ones that stayed in AppSheet's Drive folder.
export const receiptUrl = (name) => (name && !name.includes("/") ? `receipts/${name}` : null);

export const importSheet = () => call("POST", "api/import-sheet");

export const exportUrl = "api/export.csv";
