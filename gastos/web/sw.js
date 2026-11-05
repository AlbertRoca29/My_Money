// Keeps the app shell available offline. Data requests (api/…) always go to the network;
// store.js falls back to the last list it saw.
const CACHE = "gastos-v6";
const SHELL = ["./", "index.html", "style.css", "app.js", "store.js", "icon.svg", "manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Shell files: network first so edits show up at once, cache when offline.
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || /\/(api|login|logout|auth|tasks|receipts)\b/.test(url.pathname)) return;
  e.respondWith(fetch(e.request)
    .then((res) => {
      if (res.ok && res.type === "basic") { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
      return res;   // never keep a redirect to the sign-in page
    })
    .catch(() => caches.match(e.request)));
});
