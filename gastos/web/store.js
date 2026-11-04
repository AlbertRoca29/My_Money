// The only file that knows where the data lives. Today: the Flask API in routes.py.
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

// Phone photos are 2–5 MB. Receipts stay readable at 1600 px on the long side and 70% quality,
// which is about what WhatsApp does: usually 80–200 KB.
const MAX_SIDE = 1600, QUALITY = 0.7;

// Shrink a photo to WebP (JPEG where the browser can't make WebP). PDFs, and photos the browser
// can't decode (HEIC outside Safari), are sent as they are.
async function compress(file) {
  if (!file.type.startsWith("image/")) return file;
  let img;
  try { img = await createImageBitmap(file, { imageOrientation: "from-image" }); } catch { return file; }
  const scale = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";                       // transparent PNGs would turn black as JPEG
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  img.close();
  const encode = (type) => new Promise((ok) => canvas.toBlob(ok, type, QUALITY));
  let blob = await encode("image/webp");
  if (blob?.type !== "image/webp") blob = await encode("image/jpeg");
  if (!blob || blob.size >= file.size) return file;
  const ext = blob.type === "image/webp" ? ".webp" : ".jpg";
  return new File([blob], file.name.replace(/\.[^.]*$/, "") + ext, { type: blob.type });
}

// Upload a receipt photo/PDF (photos compressed first); resolves to the name to store in entry.receipt.
export async function uploadReceipt(file) {
  const form = new FormData();
  form.append("file", await compress(file));
  return (await call("POST", "api/receipts", form)).receipt;
}

// A URL to show a stored receipt, or null for old ones that stayed in Google Drive.
export const receiptUrl = (name) => (name && !name.includes("/") ? `receipts/${name}` : null);

export const importSheet = () => call("POST", "api/import-sheet");

export const exportUrl = "api/export.csv";
