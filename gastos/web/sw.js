// Keeps the app shell available offline. Data requests (api/…) always go to the network;
// store.js falls back to the last list it saw.
const CACHE = "gastos-v11";
const SHELL = ["./", "index.html", "style.css", "app.js", "store.js", "stickers.js", "icon.svg", "manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Shell files: cache first, refreshed in the background (stale-while-revalidate). The app opens at once even
// while the server is still waking up; an edit shows on the next open.
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || /\/(api|login|logout|auth|tasks|receipts|healthz)\b/.test(url.pathname)) return;
  e.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match(e.request, { ignoreSearch: true });
    const fresh = fetch(e.request).then((res) => {
      // never keep a redirect to the sign-in page
      if (res.ok && res.type === "basic" && !res.redirected) cache.put(e.request, res.clone());
      return res;
    });
    if (cached) { e.waitUntil(fresh.catch(() => {})); return cached; }
    return fresh;
  }));
});
