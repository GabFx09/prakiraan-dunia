// Prakiraan Dunia service worker: works offline with the last data seen.
// App shell: cache first, refreshed in the background.
// Data (data/*.json, raw.githubusercontent.com): network first, cache as fallback.
const VERSION = "pd-v5";
const META = "pd-meta"; // ids of alerts already notified, shared with the page
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png"];
const ALERTS_URL = "https://raw.githubusercontent.com/GabFx09/prakiraan-dunia/main/data/alerts.json";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== META).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Background check for new alerts (Chrome/Edge, installed app, roughly every 30+ minutes).
async function checkAlerts() {
  const r = await fetch(ALERTS_URL + "?t=" + Date.now(), { cache: "no-store" });
  if (!r.ok) return;
  const d = await r.json();
  const c = await caches.open(META);
  const m = await c.match("seen");
  if (!m) return; // the page has not set up notifications yet
  const seen = new Set(await m.json());
  for (const a of d.items || []) {
    if (seen.has(a.id)) continue;
    seen.add(a.id);
    if (Date.now() - new Date(a.time).getTime() > 6 * 3600e3) continue;
    await self.registration.showNotification((a.level === "kritis" ? "🔴 " : "🟠 ") + a.title, {
      body: a.body || "", icon: "icons/icon-192.png", badge: "icons/icon-192.png", tag: a.id, data: { url: a.url || "./" },
    });
  }
  await c.put("seen", new Response(JSON.stringify([...seen].slice(-300))));
}
self.addEventListener("periodicsync", (e) => { if (e.tag === "pd-alerts") e.waitUntil(checkAlerts().catch(() => {})); });

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = e.notification.data?.url || "./";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) { if ("focus" in w) { if ("navigate" in w) w.navigate(url).catch(() => {}); return w.focus(); } }
      return self.clients.openWindow(url);
    })
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
