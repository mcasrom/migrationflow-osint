const CACHE = "migrationflow-v20";
const ASSETS = ["/", "index.html", "style.css", "app.js", "i18n.js", "routes.js", "countries.geojson", "manifest.webmanifest", "icon.svg", "favicon-32.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "maskable.png", "og.png", "screenshots/mobile.png", "screenshots/wide.png", "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js", "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js", "https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js", "vendor/MarkerCluster.css", "vendor/MarkerCluster.Default.css"];

self.addEventListener("install", (e) => {
  // cache: "reload" -> ignora la caché HTTP del navegador para precachear SIEMPRE la versión nueva.
  e.waitUntil(
    caches.open(CACHE).then((c) =>
      Promise.all(ASSETS.map((a) =>
        fetch(a, { cache: "reload" }).then((r) => { if (r && r.ok) return c.put(a, r); }).catch(() => {})
      ))
    )
  );
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
  if (e.request.method !== "GET") return;
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  // Network-first con fallback a caché: siempre sirve la versión nueva cuando hay red
  // (cache: "no-cache" fuerza revalidación) y guarda una copia para offline.
  e.respondWith(
    fetch(e.request, { cache: "no-cache" })
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() =>
        caches.match(e.request).then((cached) => cached || caches.match("/"))
      )
  );
});
