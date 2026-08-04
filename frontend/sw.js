const CACHE = "migrationflow-v14";
const ASSETS = ["/", "index.html", "style.css", "app.js", "i18n.js", "routes.js", "countries.geojson", "manifest.webmanifest", "icon.svg", "favicon-32.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "maskable.png", "og.png", "screenshots/mobile.png", "screenshots/wide.png", "vendor/leaflet.js", "vendor/leaflet.css", "vendor/leaflet.markercluster.js", "vendor/leaflet-heat.js", "vendor/MarkerCluster.css", "vendor/MarkerCluster.Default.css"];

const STABLE_RE = /\.(png|svg|jpg|jpeg|webp|gif|ico|woff2?|ttf|css|js|geojson|webmanifest)$/;

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
  if (e.request.method !== "GET") return;
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  // Página principal: network-first (siempre fresca), fallback a caché.
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

  // Assets estables (js, css, imágenes, geojson): cache-first con actualización
  // en segundo plano (stale-while-revalidate). Carga instantánea offline.
  if (STABLE_RE.test(url.pathname)) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        const network = fetch(e.request)
          .then((res) => {
            if (res && res.ok) {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(e.request, copy));
            }
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
    return;
  }

  // Resto: network-first con fallback a caché.
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
