// Offline support: the app shell is cached on install, as one set, and served
// only from that set. Files are never refreshed one by one: right after a
// deploy the CDN can still return some old files, and a mix of old and new
// modules leaves a blank page. A new set arrives only with a new sw.js (the
// browser checks it on every launch, bypassing the HTTP cache), so the update
// shows up on the next launch. Bump VERSION whenever player files change.
const VERSION = 'v4';
const CACHE = `offline-listen-${VERSION}`;
const SHELL = ['./', 'index.html', 'app.js', 'lib.js', 'db.js', 'app.css', 'manifest.webmanifest',
  'icon-180.png', 'icon-512.png'];

self.addEventListener('install', (e) => {
  // cache: 'reload' skips the browser's HTTP cache, which may hold older copies
  e.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: 'reload' }))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  const key = req.mode === 'navigate' ? 'index.html' : req;
  e.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match(key, { ignoreSearch: true });
    if (cached) return cached;
    try { return await fetch(req); }
    catch { return new Response('offline', { status: 503 }); }
  }));
});
