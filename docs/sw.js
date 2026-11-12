// Service worker minimo: rende il sito installabile e usabile offline.
// Sempre prima la rete. I dati (data/, api/) non vengono mai salvati in cache: una copia vecchia
// mostrata senza avviso è peggio di un errore. Il resto (pagina, icone) resta disponibile offline.
const CACHE = "radar-v45";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())
));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  if (/\/(data|api)\//.test(u.pathname)) return;  // dati: sempre e solo dalla rete
  const key = u.origin + u.pathname;
  e.respondWith(
    fetch(e.request, {cache: "no-store"}).then(r => {
      if (r.ok) { const c = r.clone(); caches.open(CACHE).then(k => k.put(key, c)); }
      return r;
    }).catch(() => caches.match(key))
  );
});
