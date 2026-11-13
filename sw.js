// Prakiraan Dunia service worker: works offline with the last data seen.
// App shell: cache first, refreshed in the background.
// Data (data/*.json, raw.githubusercontent.com): network first, cache as fallback.
const VERSION = "pd-v4";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

const isData = (url) => url.hostname === "raw.githubusercontent.com" || /\/data\/[^/]+\.json$/.test(url.pathname);
const dataKey = (url) => "data:" + url.pathname.split("/").pop();

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (isData(url)) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(dataKey(url), copy)); }
          return res;
        })
        .catch(() => caches.open(VERSION).then((c) => c.match(dataKey(url))).then((r) => r || Response.error()))
    );
    return;
  }

  // Page navigations: network first so a new version shows at once; cached copy when offline.
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => { if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put("./index.html", copy)); } return res; })
        .catch(() => caches.open(VERSION).then((c) => c.match("./index.html")))
    );
    return;
  }

  if (url.origin === self.location.origin) {
    e.respondWith(
      caches.open(VERSION).then((c) =>
        c.match(req, { ignoreSearch: true }).then((hit) => {
          const net = fetch(req).then((res) => { if (res.ok) c.put(req, res.clone()); return res; }).catch(() => hit);
          return hit || net;
        })
      )
    );
  }
});
