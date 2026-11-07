// Gastos used to install itself as an offline phone app. It is desktop only now: this worker only exists so that
// a browser which still has the old one replaces it with this, which wipes its caches and removes itself.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    await Promise.all((await caches.keys()).map((k) => caches.delete(k)));
    await self.registration.unregister();
    for (const c of await self.clients.matchAll({ type: "window" })) c.navigate(c.url);
  })());
});
