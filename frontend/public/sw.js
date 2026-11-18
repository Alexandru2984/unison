/* Idea Evolution service worker.
 * - Hashed build assets: cache-first (they never change once published).
 * - The app shell "/": network-first, falling back to the last copy offline.
 * - Everything else (API, WebSocket, share pages, feeds) goes straight to the
 *   network and is never cached here, so public data is always current.
 */
const VERSION = "v2";
const SHELL = `shell-${VERSION}`;
const ASSETS = `assets-${VERSION}`;
const MAX_ASSETS = 60;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.add(new Request("/", { cache: "no-store" })))
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== SHELL && key !== ASSETS)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

async function trim(cache) {
  const keys = await cache.keys();
  await Promise.all(
    keys.slice(0, Math.max(0, keys.length - MAX_ASSETS)).map((key) => cache.delete(key)),
  );
}

async function asset(request) {
  const cache = await caches.open(ASSETS);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok && response.type === "basic") {
    await cache.put(request, response.clone());
    void trim(cache);
  }
  return response;
}

async function shell(request) {
  const cache = await caches.open(SHELL);
  try {
    const response = await fetch(request);
    if (response.ok && response.type === "basic")
      await cache.put("/", response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match("/");
    if (cached) return cached;
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(asset(request));
  } else if (request.mode === "navigate" && url.pathname === "/") {
    event.respondWith(shell(request));
  }
});
