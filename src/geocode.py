"""Geocoding fino para noticias: localiza subregiones/ciudades (no solo el país).

Estrategia, en orden:
1. Gazeteer local `data/gazetteer.json`: hotspots migratorios curados con coords.
   Se busca en título+descripción (insensible a tildes), el nombre más largo primero
   y restringido al país del artículo (iso3 idéntico).
2. Fallback Photon (OSM/Nominatim): token candidato extraído del título, consulta
   restringida al país (countrycode) y validada (countrycode + tipo lugar).
3. Si nada es fiable → se devuelve el centroide del país original.
Los resultados de Photon se cachean en `data/geocache.json` (evita consultas repetidas).
"""
import json
import re
import threading
import unicodedata
from pathlib import Path

import httpx

from src.config import PHOTON_API, HTTP_TIMEOUT, USER_AGENT
from src.collectors.countries import GEO

_DATA = Path(__file__).resolve().parent.parent / "data"

_GAZETTEER = json.loads((_DATA / "gazetteer.json").read_text(encoding="utf-8"))
_ISO2 = json.loads((_DATA / "iso2.json").read_text(encoding="utf-8"))

_CACHE_FILE = _DATA / "geocache.json"
_CACHE = json.loads(_CACHE_FILE.read_text(encoding="utf-8")) if _CACHE_FILE.exists() else {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 800

_PLACE_TYPES = {
    "city", "town", "village", "locality", "county", "state", "region",
    "island", "suburb", "quarter", "municipality", "hamlet", "district",
}

_GENERIC = {
    "report", "reports", "update", "updates", "situation", "situations", "bulletin",
    "assessment", "assessments", "analysis", "overview", "response", "plan", "plans",
    "needs", "summary", "summaries", "dashboard", "dashboards", "factsheet", "factsheets",
    "briefing", "briefings", "note", "notes", "status", "weekly", "monthly", "annual",
    "humanitarian", "health", "cluster", "clusters", "flash", "floods", "flood",
    "shelter", "food", "security", "livelihoods", "nutrition", "education", "protection",
    "coordination", "contributions", "water", "sanitation", "hygiene", "telecoms",
    "telecommunications", "logistics", "earthquake", "volcano", "epidemic", "dengue",
    "ebola", "drought", "no", "nos", "vol", "vols", "nr", "of", "in", "the", "on",
    "for", "and", "as", "to", "at", "by", "from", "with", "reporting", "final",
    "revised", "rev", "issue", "issued", "press", "release", "news",
}

# Variantes de nombre de país a quitar del título para aislar el token de lugar.
_COUNTRY_VARIANTS = {
    "PSE": ("palestine", "occupied palestinian territory", "occupied palestinian territories", "opt"),
    "COD": ("congo", "democratic republic of the congo", "dr congo"),
    "VEN": ("venezuela", "bolivarian republic of venezuela"),
    "TUR": ("turkiye", "türkiye"),
    "IRN": ("iran", "islamic republic of iran"),
    "RUS": ("russian federation", "russia"),
    "SYR": ("syria", "syrian arab republic"),
    "TZA": ("tanzania", "united republic of tanzania"),
    "GBR": ("united kingdom", "uk", "great britain"),
    "CIV": ("cote d'ivoire", "côte d'ivoire", "ivory coast"),
    "LAO": ("lao people's democratic republic", "laos"),
    "VNM": ("vietnam", "viet nam"),
    "SWZ": ("eswatini", "swaziland"),
    "MMR": ("myanmar", "burma"),
}

_RUN_RE = re.compile(r"(?<![A-Za-z])[A-Z][A-Za-z]+(?:[\s'-][A-Z][A-Za-z]+){0,3}")
_MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}
_GENERIC = _GENERIC | _MONTHS


def _norm(s: str) -> str:
    """Minúsculas y sin tildes (para comparar nombres con el texto de la noticia)."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _build_index():
    index = []
    for entry in _GAZETTEER:
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(_norm(entry["place"])) + r"(?![a-z0-9])")
        index.append((len(entry["place"]), pat, entry))
    index.sort(key=lambda x: x[0], reverse=True)  # nombre más largo primero
    return index


_GAZ_INDEX = _build_index()


def _gazetteer_hit(iso3: str, haystack: str):
    for _, pat, entry in _GAZ_INDEX:
        if entry["iso3"] != iso3:
            continue
        if pat.search(haystack):
            return entry
    return None


def _candidate(title: str, iso3: str):
    """Extrae un posible nombre de lugar del título (fuera del nombre del país)."""
    t = title or ""
    name = GEO.get(iso3, {}).get("name")
    if name:
        t = re.sub(r"(?i)\b" + re.escape(name) + r"\b", " ", t)
    for variant in _COUNTRY_VARIANTS.get(iso3, ()):
        t = re.sub(r"(?i)\b" + re.escape(variant) + r"\b", " ", t)
    best = None
    for run in _RUN_RE.findall(t):
        words = re.findall(r"[A-Za-z']+", run)
        if not words:
            continue
        if any(w.lower() in _GENERIC for w in words):
            continue
        if len(run) < 4:
            continue
        if best is None or len(run) > len(best):
            best = run
    return best


def _save_cache():
    try:
        _CACHE_FILE.write_text(json.dumps(_CACHE, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _photon(token: str, iso3: str):
    cc = _ISO2.get(iso3)
    if not cc:
        return None
    key = f"{iso3}:{_norm(token)}"
    with _CACHE_LOCK:
        if key in _CACHE:
            return _CACHE[key]
    try:
        r = httpx.get(PHOTON_API,
                      params={"q": token, "limit": 5, "countrycode": cc},
                      headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        result = None
        for f in r.json().get("features", []):
            p = f.get("properties", {})
            if p.get("countrycode") != cc:
                continue
            if p.get("osm_key") == "place" or p.get("type") in _PLACE_TYPES:
                lon, lat = f["geometry"]["coordinates"]
                result = {"lat": round(lat, 4), "lon": round(lon, 4),
                          "name": p.get("name") or token}
                break
    except (httpx.HTTPError, ValueError):
        result = None
    with _CACHE_LOCK:
        _CACHE[key] = result
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _save_cache()
    return result


def refine(iso3: str, lat: float, lon: float, title: str, description: str):
    """Devuelve {lat, lon, name} con la posición fina, o el centroide original (name=None)."""
    if not iso3:
        return {"lat": lat, "lon": lon, "name": None}
    title_n = _norm(title)
    desc_n = _norm(description)

    entry = _gazetteer_hit(iso3, title_n) or _gazetteer_hit(iso3, f"{title_n} {desc_n}")
    if entry:
        return {"lat": entry["lat"], "lon": entry["lon"], "name": entry["place"]}

    token = _candidate(title, iso3)
    if token:
        result = _photon(token, iso3)
        if result:
            return result

    return {"lat": lat, "lon": lon, "name": None}
