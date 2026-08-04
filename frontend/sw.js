const CACHE = "migrationflow-v13";
const ASSETS = ["/", "index.html", "style.css", "app.js", "i18n.js", "routes.js", "countries.geojson", "manifest.webmanifest", "icon.svg", "favicon-32.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "maskable.png", "og.png", "vendor/leaflet.js", "vendor/leaflet.css", "vendor/leaflet.markercluster.js", "vendor/leaflet-heat.js", "vendor/MarkerCluster.css", "vendor/MarkerCluster.Default.css"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("push", (e) => {
  let data = { title: "MigrationFlow OSINT", body: "", url: "/" };
  try { data = Object.assign(data, e.data.json()); } catch { }
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon || "/icon-192.png",
      badge: data.badge || "/icon-192.png",
      data: { url: data.url || "/" },
      tag: data.tag || "migrationflow",
      renotify: false,
    })
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return clients.openWindow(url);
  }));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request).then((cached) => cached || caches.match("/")))
  );
});
