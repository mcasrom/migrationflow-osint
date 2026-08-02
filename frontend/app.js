/* MigrationFlow OSINT — frontend Leaflet */
const LEVEL_RANK = { info: 0, warning: 1, alert: 2, critical: 3 };
const LEVEL_COLOR = { info: "#4a9eff", warning: "#ffb020", alert: "#ff7043", critical: "#f43f5e" };
const LEVEL_LABEL = { info: "info", warning: "warning", alert: "alert", critical: "critical" };

const TYPE_ORDER = ["refugees", "asylum", "idp", "displacement", "dtm_idp", "refugees_origin", "missing"];
const TYPE_DEFAULT_HIDDEN = ["refugees_origin"];
const KOFI_URL = "https://ko-fi.com/migrationflow";

let map, darkLayer, lightLayer, layers = {}, heatLayer = null;
let state = { minLevel: "info", heat: false, dark: true };
const enabledTypes = new Set();
let summary = null, status = null;

function initTabs() {
  const switchTab = (name) => {
    document.getElementById("tab-data").classList.toggle("active", name === "data");
    document.getElementById("tab-info").classList.toggle("active", name === "info");
    document.getElementById("pane-data").classList.toggle("hidden", name !== "data");
    document.getElementById("pane-info").classList.toggle("hidden", name !== "info");
  };
  document.getElementById("tab-data").addEventListener("click", () => switchTab("data"));
  document.getElementById("tab-info").addEventListener("click", () => switchTab("info"));
  document.getElementById("kofiBtn").href = KOFI_URL;
  document.getElementById("exportBtn").addEventListener("click", (e) => {
    e.preventDefault();
    exportGeoJSON();
  });
}

async function exportGeoJSON() {
  try {
    const r = await fetch("/api/events?limit=5000");
    const data = await r.json();
    const feats = data.events.map(ev => ({
      type: "Feature",
      properties: {
        source: ev.source, event_type: ev.event_type, level: ev.level,
        title: ev.title, value: ev.value, country: ev.country,
        reported_at: ev.reported_at, source_id: ev.source_id,
      },
      geometry: { type: "Point", coordinates: [ev.lon, ev.lat] },
    }));
    const blob = new Blob([JSON.stringify({ type: "FeatureCollection", features: feats }, null, 2)],
      { type: "application/geo+json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "migrationflow_events.geojson";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch { }
}

function fmt(n) { return (n == null) ? "—" : Number(n).toLocaleString("es-ES"); }

function initMap() {
  darkLayer = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO', subdomains: "abcd", maxZoom: 19 });
  lightLayer = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO', subdomains: "abcd", maxZoom: 19 });
  map = L.map("map", { zoomControl: true, attributionControl: true, center: [25, 10], zoom: 3, minZoom: 2 });
  darkLayer.addTo(map);

  for (const t of TYPE_ORDER) {
    layers[t] = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 55 });
    layers[t].addTo(map);
    enabledTypes.add(t);
  }
}

function buildTypeFilters(eventTypes) {
  const box = document.getElementById("typeFilters");
  box.innerHTML = "";
  for (const t of TYPE_ORDER) {
    const label = (eventTypes && eventTypes[t]) || t;
    const hidden = TYPE_DEFAULT_HIDDEN.includes(t);
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.dataset.type = t;
    if (!hidden) btn.classList.add("active");
    else enabledTypes.delete(t);
    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      const on = btn.classList.contains("active");
      if (on) enabledTypes.add(t); else enabledTypes.delete(t);
      if (on) { if (!map.hasLayer(layers[t])) layers[t].addTo(map); }
      else map.removeLayer(layers[t]);
      updateSummary();
    });
    box.appendChild(btn);
  }
}

function initControls(eventTypes) {
  buildTypeFilters(eventTypes);
  document.querySelectorAll("#levelFilters button").forEach(b => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#levelFilters button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      state.minLevel = b.dataset.level;
      refreshEvents();
    });
  });
  document.getElementById("heatToggle").addEventListener("change", e => {
    state.heat = e.target.checked;
    refreshEvents();
  });
  document.getElementById("darkToggle").addEventListener("change", e => {
    state.dark = e.target.checked;
    if (state.dark) { map.removeLayer(lightLayer); darkLayer.addTo(map); }
    else { map.removeLayer(darkLayer); lightLayer.addTo(map); }
  });
}

function iconFor(ev) {
  const color = LEVEL_COLOR[ev.level] || LEVEL_COLOR.info;
  return L.divIcon({
    className: "flow-marker",
    html: `<div style="background:${color}"></div>`,
    iconSize: [14, 14], iconAnchor: [7, 7], popupAnchor: [0, -8],
  });
}

function radiusFor(ev) {
  if (ev.event_type === "missing") return 6;
  const v = Math.max(1, Number(ev.value) || 1);
  return Math.min(22, 5 + Math.sqrt(v) / 40);
}

function popupHtml(ev) {
  const lvl = LEVEL_LABEL[ev.level] || ev.level;
  const when = ev.reported_at ? new Date(ev.reported_at).toLocaleDateString("es-ES") : "—";
  return `<div class="popup">
    <h3>${(ev.title || ev.event_type).replace(/</g, "&lt;")}</h3>
    <span class="lvl lvl-${lvl}">${lvl.toUpperCase()}</span>
    <div class="val">${fmt(ev.value)}</div>
    <div class="meta">${when} · ${ev.source} · ${ev.country || ev.iso3 || ""}</div>
    ${ev.description ? `<div class="desc">${ev.description.replace(/</g, "&lt;")}</div>` : ""}
  </div>`;
}

function placeEvent(ev) {
  if (!enabledTypes.has(ev.event_type)) return;
  if (LEVEL_RANK[ev.level] < LEVEL_RANK[state.minLevel]) return;
  const marker = L.marker([ev.lat, ev.lon], { icon: iconFor(ev), title: ev.title });
  marker.bindPopup(popupHtml(ev));
  marker.on("mouseover", () => marker.openPopup());
  marker.on("mouseout", () => marker.closePopup());
  layers[ev.event_type].addLayer(marker);
}

async function refreshEvents() {
  const types = [...enabledTypes].join(",");
  const url = `/api/events?types=${encodeURIComponent(types)}&min_level=${state.minLevel}&limit=5000`;
  let data;
  try {
    const r = await fetch(url);
    data = await r.json();
  } catch { return; }
  for (const t of TYPE_ORDER) layers[t].clearLayers();
  if (heatLayer) { map.removeLayer(heatLayer); heatLayer = null; }
  const heatPts = [];
  for (const ev of data.events) {
    placeEvent(ev);
    if (ev.event_type === "missing") {
      const w = Math.min(1, Math.log10(Math.max(1, Number(ev.value) || 1)) / 3);
      heatPts.push([ev.lat, ev.lon, w]);
    }
  }
  if (state.heat && heatPts.length) {
    heatLayer = L.heatLayer(heatPts, { radius: 28, blur: 22, maxZoom: 5,
      gradient: { 0.2: "#ffb020", 0.5: "#ff7043", 0.8: "#f43f5e", 1: "#ff0040" } });
    heatLayer.addTo(map);
  }
  document.getElementById("lastUpdate").textContent =
    `Actualizado ${new Date().toLocaleTimeString("es-ES")}`;
}

async function updateSummary() {
  if (!summary) return;
  const box = document.getElementById("summaryBox");
  const visible = summary.by_type || {};
  let rows = "";
  for (const t of TYPE_ORDER) {
    if (!enabledTypes.has(t)) continue;
    const n = visible[t] || 0;
    rows += `<div class="row"><span><span class="dot" style="background:${LEVEL_COLOR.info}"></span>${TYPE_LABEL(t)}</span><b>${fmt(n)}</b></div>`;
  }
  rows += `<div class="row"><span>Total activos</span><b>${fmt(summary.total_active)}</b></div>`;
  box.innerHTML = rows;
}

function TYPE_LABEL(t) {
  if (status && status.event_types && status.event_types[t]) return status.event_types[t];
  return t;
}

async function updateSources() {
  if (!status) return;
  const box = document.getElementById("sourcesBoxInfo");
  let html = "";
  for (const c of status.collectors || []) {
    const ok = c.success;
    const when = c.finished_at ? new Date(c.finished_at).toLocaleString("es-ES") : "—";
    html += `<div class="row">
      <span><span class="dot ${ok ? "ok" : "err"}"></span>${c.collector}</span>
      <span class="${ok ? "ok" : "err"}">${ok ? `+${c.events_created}` : "error"}</span>
    </div>
    <div style="font-size:10px;color:var(--muted);padding-left:15px;margin-bottom:3px">${when}</div>`;
  }
  box.innerHTML = html || "Sin ejecuciones todavía";
}

async function loadAll() {
  try {
    const [s, st] = await Promise.all([fetch("/api/summary"), fetch("/api/status")]);
    summary = await s.json();
    status = await st.json();
    document.getElementById("totalBadge").textContent = `${fmt(summary.total_active)} eventos`;
    initControls(status.event_types);
    updateSummary();
    updateSources();
  } catch { }
  await refreshEvents();
}

initMap();
initTabs();
loadAll();
setInterval(loadAll, 300000);
