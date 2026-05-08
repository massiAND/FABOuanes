const VERSION = "fabouanes-v29-nav-hide-perf";
const STATIC_CACHE = `${VERSION}-static`;
const RUNTIME_CACHE = `${VERSION}-runtime`;
const OFFLINE_URL = "/static/offline.html";
const MAX_RUNTIME_ENTRIES = 40;
const PRECACHE = [
  OFFLINE_URL,
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/favicon.png",
  "/static/fab_logo.png",
  "/static/desktop_logo_shield.png",
  "/static/dashboard.png",
  "/static/fab_invoice_logo.png",
  "/static/fab_invoice_logo_clean.png",
  "/static/app.css",
  "/static/app.js",
  "/static/css/tokens.css",
  "/static/css/components.css",
  "/static/js/api.js",
  "/static/js/forms.js",
  "/static/js/theme.js",
  "/static/js/layout.js",
  "/static/js/tables.js",
  "/static/js/notifications.js",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
  "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => cache.addAll(PRECACHE).catch(() => null)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => ![STATIC_CACHE, RUNTIME_CACHE].includes(key)).map(key => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("message", event => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(STATIC_CACHE);
  cache.put(request, response.clone());
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    const cache = await caches.open(RUNTIME_CACHE);
    cache.put(request, response.clone());
    trimCache(RUNTIME_CACHE, MAX_RUNTIME_ENTRIES);
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") {
      return caches.match(OFFLINE_URL);
    }
    throw error;
  }
}

async function trimCache(cacheName, maxEntries) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length <= maxEntries) return;
  await cache.delete(keys[0]);
  return trimCache(cacheName, maxEntries);
}

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  const isStaticAsset = url.origin === self.location.origin && (
    url.pathname.startsWith("/static/") ||
    url.pathname.endsWith(".css") ||
    url.pathname.endsWith(".js") ||
    url.pathname.endsWith(".png") ||
    url.pathname.endsWith(".jpg") ||
    url.pathname.endsWith(".svg")
  );
  const isApiGet = url.origin === self.location.origin && url.pathname.startsWith("/api/");
  const isDocument = event.request.mode === "navigate" || event.request.headers.get("accept")?.includes("text/html");

  if (isStaticAsset || url.hostname.includes("jsdelivr")) {
    event.respondWith(cacheFirst(event.request));
    return;
  }
  if (isApiGet || isDocument) {
    event.respondWith(networkFirst(event.request));
  }
});
