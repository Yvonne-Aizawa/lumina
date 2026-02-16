const CACHE_NAME = "lumi-v1";

const PRECACHE_URLS = [
    "/",
    "/static/css/style.css",
    "/static/js/app.js",
    "/static/js/auth.js",
    "/static/js/scene.js",
    "/static/js/animations.js",
    "/static/js/websocket.js",
    "/static/js/chat.js",
    "/static/js/wakeword.js",
    "/static/js/settings.js",
    "/static/icon-192.png",
    "/static/icon.png",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);

    // Never cache API calls, WebSocket upgrades, or auth endpoints
    if (
        url.pathname.startsWith("/api/") ||
        url.pathname.startsWith("/ws") ||
        event.request.method !== "GET"
    ) {
        return;
    }

    // Network-first for HTML pages (always get fresh content)
    if (event.request.mode === "navigate") {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
        return;
    }

    // Cache-first for static assets
    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) return cached;
            return fetch(event.request).then((response) => {
                // Cache successful responses for static assets
                if (response.ok && url.pathname.startsWith("/static/")) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) =>
                        cache.put(event.request, clone)
                    );
                }
                return response;
            });
        })
    );
});
