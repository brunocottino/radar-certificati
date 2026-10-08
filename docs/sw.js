// Service worker minimo: rende il sito installabile e usabile offline con gli ultimi dati scaricati.
// Sempre prima la rete (dati freschi), la cache solo se si è offline.
const CACHE = "radar-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  const key = u.origin + u.pathname;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok) { const c = r.clone(); caches.open(CACHE).then(k => k.put(key, c)); }
      return r;
    }).catch(() => caches.match(key))
  );
});
