/* MigrationFlow OSINT — frontend Leaflet */
const LEVEL_RANK = { info: 0, warning: 1, alert: 2, critical: 3 };
const LEVEL_COLOR = { info: "#4a9eff", warning: "#ffb020", alert: "#ff7043", critical: "#f43f5e" };
const KOFI_URL = "https://ko-fi.com/m_castillo";

const TYPE_ORDER = ["refugees", "asylum", "idp", "displacement", "dtm_idp", "refugees_origin", "missing", "news"];
const TYPE_DEFAULT_HIDDEN = ["refugees_origin", "news"];

let map, darkLayer, lightLayer, layers = {}, heatLayer = null, routesLayer = null;
let countryLayer = null, isoToLayer = new Map(), nameToIso = new Map();
let lastEvents = [];
let state = { minLevel: "info", heat: false, dark: true, year: "" };
const enabledTypes = new Set();
let summary = null, status = null;

function fmt(n) {
  if (n == null) return "—";
  const locale = LANG === "en" ? "en-US" : "es-ES";
  return Number(n).toLocaleString(locale);
}
function fmtDate(d) {
  const locale = LANG === "en" ? "en-US" : "es-ES";
  return new Date(d).toLocaleDateString(locale);
}
function fmtTime(d) {
  const locale = LANG === "en" ? "en-US" : "es-ES";
  return new Date(d).toLocaleString(locale);
}

function initTabs() {
  const switchTab = (name) => {
    document.getElementById("tab-data").classList.toggle("active", name === "data");
    document.getElementById("tab-info").classList.toggle("active", name === "info");
    document.getElementById("tab-about").classList.toggle("active", name === "about");
    document.getElementById("pane-data").classList.toggle("hidden", name !== "data");
    document.getElementById("pane-info").classList.toggle("hidden", name !== "info");
    document.getElementById("pane-about").classList.toggle("hidden", name !== "about");
  };
  document.getElementById("tab-data").addEventListener("click", () => switchTab("data"));
  document.getElementById("tab-info").addEventListener("click", () => switchTab("info"));
  document.getElementById("tab-about").addEventListener("click", () => switchTab("about"));
  document.getElementById("kofiBtn").href = KOFI_URL;
  document.getElementById("exportBtn").addEventListener("click", (e) => { e.preventDefault(); exportGeoJSON(); });
  document.getElementById("exportCsvBtn").addEventListener("click", (e) => { e.preventDefault(); exportCSV(); });
}

const CSV_FIELDS = ["source", "source_id", "event_type", "category", "level",
  "title", "country", "iso3", "admin_level", "value", "value_type",
  "lat", "lon", "reported_at", "updated_at", "description"];

function csvCell(v) {
  const s = (v == null) ? "" : String(v);
  return '"' + s.replace(/"/g, '""') + '"';
}

async function exportCSV() {
  try {
    const r = await fetch("/api/events?limit=5000");
    const data = await r.json();
    const rows = data.events.map(ev => CSV_FIELDS.map(f => csvCell(ev[f])).join(","));
    const csv = "\ufeff" + CSV_FIELDS.join(",") + "\r\n" + rows.join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "migrationflow_events.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch { }
}

function initKofi() {
  const btn = document.getElementById("kofiFloat");
  if (!btn) return;
  btn.href = KOFI_URL;
  let count = parseInt(localStorage.getItem("mf_kofi_loads") || "0");
  count += 1;
  localStorage.setItem("mf_kofi_loads", String(count));
  if (count >= 2) {
    btn.classList.add("show");
    const msgs = ["☕ Invítame un café", "❤️ Apoya el proyecto",
      "☕ ¿Útil? Invítame un café", "🍺 Invítame una cerveza"];
    btn.textContent = msgs[Math.floor(Math.random() * msgs.length)];
  }
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

function initIntro() {
  const intro = document.getElementById("intro");
  if (!intro) return;
  const close = () => {
    intro.classList.add("hidden");
    try { localStorage.setItem("mf_intro_seen", "1"); } catch { }
  };
  const closeBtn = document.getElementById("introClose");
  if (closeBtn) closeBtn.addEventListener("click", close);
  const goBtn = document.getElementById("introGo");
  if (goBtn) goBtn.addEventListener("click", close);
  const srcLink = document.getElementById("introSources");
  if (srcLink) srcLink.addEventListener("click", (e) => {
    e.preventDefault();
    close();
    document.getElementById("tab-info").click();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !intro.classList.contains("hidden")) close(); });
  if (localStorage.getItem("mf_intro_seen") === "1") {
    intro.classList.add("hidden");
  } else {
    introStats().then(() => { });
  }
}

async function introStats() {
  const box = document.getElementById("introStats");
  try {
    const [s, st] = await Promise.all([fetch("/api/summary"), fetch("/api/status")]);
    const sum = await s.json();
    const stat = await st.json();
    const okSources = (stat.collectors || []).filter(c => c.success).length;
    const totalSources = (stat.collectors || []).length;
    const affected = (sum.with_value && sum.sum_value) ? sum.sum_value : null;
    box.innerHTML = `
      <div class="intro-stat"><b>${fmt(sum.total_active)}</b><span>${t("st_events")}</span></div>
      <div class="intro-stat"><b>${okSources}/${totalSources}</b><span>${t("st_sources")}</span></div>
      <div class="intro-stat"><b>${affected == null ? "—" : fmt(affected)}</b><span>${t("st_people")}</span></div>`;
  } catch {
    box.innerHTML = "";
  }
}

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

  routesLayer = L.layerGroup();
  for (const route of MIGRATION_ROUTES) {
    L.polyline(route.points, { color: route.color, weight: 2.5, opacity: 0.75, dashArray: "6 6" })
      .bindPopup(`<b>${route.name}</b>`)
      .addTo(routesLayer);
  }
}

function buildTypeFilters(eventTypes) {
  const box = document.getElementById("typeFilters");
  box.innerHTML = "";
  for (const t of TYPE_ORDER) {
    const label = typeLabel(t, (eventTypes && eventTypes[t]) || t);
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
      if (state.choropleth) {
        applyChoropleth(lastEvents.filter(ev => enabledTypes.has(ev.event_type)));
      }
      updateSummary();
    });
    box.appendChild(btn);
  }
}

function populateYears() {
  const sel = document.getElementById("yearFilter");
  for (let i = sel.options.length - 1; i >= 1; i--) sel.remove(i);
  const current = new Date().getFullYear();
  for (let y = current; y >= 2023; y--) {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    sel.appendChild(opt);
  }
}

const CHORO_BASE_STYLE = { weight: 1, opacity: 0.85, color: "#334155", fillOpacity: 0.72 };
const CHORO_RAMP = [[251, 230, 214], [254, 200, 132], [253, 141, 60], [217, 72, 15], [140, 45, 4]];

function normName(n) { return String(n || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); }

function isoOfFeature(f) {
  const p = f.properties || {};
  const iso = p.ISO_A3 && p.ISO_A3 !== "-99" ? p.ISO_A3 : (p.ISO_N3 ? p.ISO_N3 : null);
  return iso;
}

async function loadCountryLayer() {
  if (countryLayer) return;
  const r = await fetch("countries.geojson");
  const gj = await r.json();
  for (const f of gj.features || []) {
    const iso = isoOfFeature(f);
    const name = normName(f.properties.NAME || f.properties.ADMIN || "");
    if (iso && name) nameToIso.set(name, iso);
  }
  countryLayer = L.geoJSON(gj, {
    style: CHORO_BASE_STYLE,
    onEachFeature: (f, layer) => {
      const iso = isoOfFeature(f);
      if (iso) {
        isoToLayer.set(iso, layer);
        layer.bindPopup("", { maxWidth: 340 });
        layer.on("click", async () => {
          layer.setPopupContent(`<div class="popup">${t("cp_loading")}</div>`);
          layer.openPopup();
          const data = await loadCountrySummary(iso, COUNTRY_SUMMARY_DAYS);
          if (!data) { layer.setPopupContent(`<div class="popup cp-none">${t("cp_error")}</div>`); return; }
          layer.setPopupContent(countryPopupHtml(data));
          layer.openPopup();
        });
      }
      layer.bindTooltip("", { sticky: true, direction: "top" });
    },
  });
}

function choroplethColor(frac) {
  const f = Math.min(1, Math.max(0, frac));
  const scaled = f * (CHORO_RAMP.length - 1);
  const i = Math.min(CHORO_RAMP.length - 2, Math.floor(scaled));
  const t = scaled - i;
  const a = CHORO_RAMP[i], b = CHORO_RAMP[i + 1];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function eventIso3(ev) {
  if (ev.iso3) return ev.iso3;
  const n = normName(ev.country);
  return n ? nameToIso.get(n) || null : null;
}

const COUNTRY_SUMMARY_DAYS = 365;
const countrySummaryCache = new Map();

function esc(s) { return String(s == null ? "" : s).replace(/</g, "&lt;"); }

async function loadCountrySummary(iso, days) {
  const key = `${iso}|${days}`;
  if (countrySummaryCache.has(key)) return countrySummaryCache.get(key);
  try {
    const r = await fetch(`/api/country/${encodeURIComponent(iso)}?days=${days}`);
    if (!r.ok) return null;
    const data = await r.json();
    countrySummaryCache.set(key, data);
    return data;
  } catch { return null; }
}

function fmtDelta(cur, prev) {
  if (prev == null || cur == null) return { txt: "", cls: "" };
  if (prev === 0) return { txt: cur > 0 ? "▲" : "", cls: cur > 0 ? "up" : "flat" };
  const pct = Math.round(((cur - prev) / prev) * 100);
  if (pct === 0) return { txt: "▬ 0%", cls: "flat" };
  return { txt: `${pct > 0 ? "▲" : "▼"} ${pct > 0 ? "+" : ""}${pct}%`, cls: pct > 0 ? "up" : "down" };
}

function countryPopupHtml(d) {
  const st = d.stocks || [];
  const act = d.activity || {};
  const dl = d.delta || {};
  let html = `<div class="popup country-popup">
    <h3>${esc(d.name) || d.iso3}</h3>
    <div class="meta">${d.iso3} · ${t("cp_affected")}: <b>${d.affected != null ? fmt(d.affected) : "—"}</b></div>`;
  if (st.length) {
    const asof = st[0].reported_at ? fmtDate(st[0].reported_at) : "";
    html += `<div class="cp-sub">${t("cp_stocks")}${asof ? ` <span class="cp-date">(${t("cp_latest")} ${asof})</span>` : ""}</div>
      <table class="cp-table">` +
      st.map(s => `<tr><td>${typeLabel(s.type, s.type)}</td><td class="cp-v">${fmt(s.value)}</td></tr>`).join("") +
      `</table>`;
  } else {
    html += `<div class="cp-none">${t("cp_no_stock")}</div>`;
  }
  const keys = Object.keys(act);
  if (keys.length) {
    html += `<div class="cp-sub">${t("cp_activity").replace("{d}", fmt(d.days || COUNTRY_SUMMARY_DAYS))}</div>`;
    for (const k of keys) {
      const a = act[k];
      if (k === "missing") {
        const dlt = fmtDelta(a.count, dl.missing ? dl.missing.count : null);
        html += `<div class="cp-row"><span>${t("cp_deaths")}</span><b>${fmt(a.sum)}</b><span class="cp-delta ${dlt.cls}">${dlt.txt}</span></div>
          <div class="cp-row"><span>${t("cp_incidents")}</span><b>${fmt(a.count)}</b></div>`;
      } else if (k === "news") {
        const dlt = fmtDelta(a.count, dl.news ? dl.news.count : null);
        html += `<div class="cp-row"><span>${t("cp_news")}</span><b>${fmt(a.count)}</b><span class="cp-delta ${dlt.cls}">${dlt.txt}</span></div>`;
      } else {
        html += `<div class="cp-row"><span>${typeLabel(k, k)}</span><b>${fmt(a.sum)}</b></div>`;
      }
    }
    if (dl.missing || dl.news) html += `<div class="cp-foot">${t("cp_vs")}</div>`;
  } else {
    html += `<div class="cp-none">${t("cp_none")}</div>`;
  }
  if (act.missing) html += `<div class="cp-note">⚠ ${t("cp_note_deaths")}</div>`;
  return html + `</div>`;
}

function updateChoroplethLegend(max, count) {
  const legend = document.getElementById("choroplethLegend");
  if (!state.choropleth) { legend.classList.add("hidden"); return; }
  legend.classList.remove("hidden");
  legend.querySelector(".cl-title").textContent = t("ch_legend");
  legend.querySelector(".cl-min").textContent = "0";
  legend.querySelector(".cl-max").textContent = max > 0 ? fmt(max) : "—";
}

function applyChoropleth(events) {
  if (!state.choropleth) {
    if (countryLayer) countryLayer.setStyle(CHORO_BASE_STYLE);
    updateChoroplethLegend(0, 0);
    return;
  }
  if (!countryLayer || !map.hasLayer(countryLayer)) return;
  const sums = new Map();
  for (const ev of events) {
    const iso = eventIso3(ev);
    if (!iso) continue;
    const v = Number(ev.value) || 0;
    const cur = sums.get(iso) || { sum: 0, count: 0 };
    cur.sum += v; cur.count += 1;
    sums.set(iso, cur);
  }
  let max = 0;
  sums.forEach(c => { if (c.sum > max) max = c.sum; });
  isoToLayer.forEach((layer, iso) => {
    const data = sums.get(iso);
    if (!data) {
      layer.setStyle({ ...CHORO_BASE_STYLE, fillColor: "#1e293b", fillOpacity: 0.35 });
      layer.setTooltipContent("");
      return;
    }
    const frac = max > 0 ? Math.log10(data.sum + 1) / Math.log10(max + 1) : 0;
    layer.setStyle({ ...CHORO_BASE_STYLE, fillColor: choroplethColor(frac) });
    layer.setTooltipContent(
      `<b>${iso}</b><br>${fmt(data.sum)} · ${data.count} ${t("ch_events_n")}`);
  });
  updateChoroplethLegend(max, sums.size);
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
  document.getElementById("yearFilter").addEventListener("change", e => {
    state.year = e.target.value;
    refreshEvents();
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
  document.getElementById("routesToggle").addEventListener("change", e => {
    if (e.target.checked) routesLayer.addTo(map);
    else map.removeLayer(routesLayer);
  });
  document.getElementById("choroplethToggle").addEventListener("change", async e => {
    state.choropleth = e.target.checked;
    if (state.choropleth) {
      try {
        await loadCountryLayer();
        if (!map.hasLayer(countryLayer)) countryLayer.addTo(map);
        refreshEvents();
      } catch { }
    } else {
      if (countryLayer && map.hasLayer(countryLayer)) map.removeLayer(countryLayer);
      updateChoroplethLegend(0, 0);
      refreshEvents();
    }
  });
  document.getElementById("langToggle").addEventListener("click", () => {
    LANG = LANG === "es" ? "en" : "es";
    localStorage.setItem("mf_lang", LANG);
    applyLang();
    buildTypeFilters(status ? status.event_types : null);
    populateYears();
    updateSummary();
    updateSources();
    refreshEvents();
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
  const lvl = levelLabel(ev.level);
  const when = ev.reported_at ? fmtDate(ev.reported_at) : "—";
  return `<div class="popup">
    <h3>${(ev.title || ev.event_type).replace(/</g, "&lt;")}</h3>
    <span class="lvl lvl-${ev.level}">${lvl.toUpperCase()}</span>
    <div class="val">${fmt(ev.value)}</div>
    <div class="meta">${when} · ${ev.source} · ${ev.country || ev.iso3 || ""}</div>
    ${ev.description ? `<div class="desc">${ev.description.replace(/</g, "&lt;")}</div>` : ""}
  </div>`;
}

function placeEvent(ev) {
  if (!enabledTypes.has(ev.event_type)) return;
  if (LEVEL_RANK[ev.level] < LEVEL_RANK[state.minLevel]) return;
  const layer = layers[ev.event_type];
  if (!layer || typeof layer.addLayer !== "function") return;
  const marker = L.marker([ev.lat, ev.lon], { icon: iconFor(ev), title: ev.title });
  const iso = ev.iso3 || eventIso3(ev);
  marker.bindPopup(popupHtml(ev) + (iso
    ? `<div class="popup-footer"><button class="popup-btn" data-iso3="${iso}">${t("cp_btn")}</button></div>`
    : ""));
  marker.on("mouseover", () => marker.openPopup());
  marker.on("mouseout", () => marker.closePopup());
  marker.on("popupopen", () => {
    const btn = marker.getPopup().getElement()?.querySelector(".popup-btn");
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      const p = marker.getPopup();
      p.setContent(`<div class="popup">${t("cp_loading")}</div>`);
      const data = await loadCountrySummary(btn.dataset.iso3, COUNTRY_SUMMARY_DAYS);
      if (!data) { p.setContent(`<div class="popup cp-none">${t("cp_error")}</div>`); return; }
      p.setContent(countryPopupHtml(data));
      p.update();
    });
    L.DomEvent.disableClickPropagation(btn);
  });
  layer.addLayer(marker);
}

async function refreshEvents() {
  const types = [...enabledTypes].join(",");
  const params = new URLSearchParams({ types, min_level: state.minLevel, limit: "5000" });
  if (state.year) params.set("year", state.year);
  let data;
  try {
    const r = await fetch(`/api/events?${params}`);
    data = await r.json();
  } catch { return; }
  const events = (data && Array.isArray(data.events)) ? data.events : [];
  lastEvents = events;
  for (const t of TYPE_ORDER) layers[t].clearLayers();
  if (heatLayer) { map.removeLayer(heatLayer); heatLayer = null; }
  const heatPts = [];
  for (const ev of events) {
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
  applyChoropleth(events);
  document.getElementById("lastUpdate").textContent = `${t("updated")} ${fmtTime(new Date())}`;
}

async function updateSummary() {
  if (!summary) return;
  const box = document.getElementById("summaryBox");
  const visible = summary.by_type || {};
  let rows = "";
  for (const tt of TYPE_ORDER) {
    if (!enabledTypes.has(tt)) continue;
    const n = visible[tt] || 0;
    rows += `<div class="row"><span><span class="dot" style="background:${LEVEL_COLOR.info}"></span>${typeLabel(tt, TYPE_LABEL(tt))}</span><b>${fmt(n)}</b></div>`;
  }
  rows += `<div class="row"><span>${t("no_total")}</span><b>${fmt(summary.total_active)}</b></div>`;
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
    const when = c.finished_at ? fmtTime(c.finished_at) : "—";
    html += `<div class="row">
      <span><span class="dot ${ok ? "ok" : "err"}"></span>${c.collector}</span>
      <span class="${ok ? "ok" : "err"}">${ok ? `+${c.events_created}` : t("t_error")}</span>
    </div>
    <div style="font-size:10px;color:var(--muted);padding-left:15px;margin-bottom:3px">${when}</div>`;
  }
  box.innerHTML = html || t("t_no_runs");
}

let controlsBound = false;

async function loadAll() {
  try {
    const [s, st] = await Promise.all([fetch("/api/summary"), fetch("/api/status")]);
    summary = await s.json();
    status = await st.json();
    document.getElementById("totalBadge").innerHTML =
      `${fmt(summary.total_active)} <span data-i18n="events">${t("events")}</span>`;
    if (!controlsBound) {
      controlsBound = true;
      initControls(status.event_types);
    }
    updateSummary();
    updateSources();
  } catch { }
  await refreshEvents();
}

applyLang();
initIntro();
initTabs();
populateYears();
try { initMap(); } catch (e) { console.error("initMap:", e); }
try { initKofi(); } catch (e) { console.error("initKofi:", e); }
loadCountryLayer().catch(() => { });
loadAll();
setInterval(loadAll, 300000);
