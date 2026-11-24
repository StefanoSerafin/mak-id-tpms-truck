// ID TPMS TRUCK - cache per l'uso senza rete (prima la rete, poi la cache)
// Se cambiano i file precaricati, aumentare il numero di versione.
const C = 'id-tpms-truck-v1';
const FILES = ['./', './index.html', './lettore.js', './modelli.js', './manifest.webmanifest', './logo-mate-nero.svg', './icon-180.png', './icon-192.png', './icon-512.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(C).then(c => c.addAll(FILES))); self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== C).map(x => caches.delete(x)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  // solo i file dell'app: le chiamate all'API passano sempre dalla rete
  if (e.request.method !== 'GET' || !e.request.url.startsWith(self.location.origin)) return;
  const rete = fetch(e.request).then(r => { if (r.ok) { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); } return r; });
  const attesa = new Promise(res => setTimeout(res, 3500));
  e.respondWith((async () => {
    const cached = await caches.match(e.request, { ignoreSearch: true });
    try {
      if (cached) { const r = await Promise.race([rete, attesa]); return r || cached; }
      return await rete;
    } catch (err) { return cached || caches.match('./index.html'); }
  })());
});
