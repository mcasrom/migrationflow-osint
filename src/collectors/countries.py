import json
import re
from pathlib import Path

_GEO_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "countries_geo.json"
GEO = json.loads(_GEO_FILE.read_text(encoding="utf-8"))

# Aliases ISO3 no oficiales / no estándar
_ALIASES = {
    "XKX": "KOS",          # Kosovo
    "KOS": "KOS",
    "PSX": "PSE",          # Palestina
    "WBC": None,
    "SRB": "SRB",
}

_NAME_FALLBACK = {v["name"].lower(): k for k, v in GEO.items()}

_NAME_VARIANTS = {
    "türkiye": "TUR", "turkey": "TUR",
    "venezuela": "VEN",
    "iran": "IRN", "iran (islamic republic of)": "IRN",
    "russian federation": "RUS", "russia": "RUS",
    "lao people's democratic republic": "LAO", "laos": "LAO",
    "syria": "SYR", "syrian arab republic": "SYR",
    "democratic republic of the congo": "COD", "dr congo": "COD",
    "congo (the democratic republic of the)": "COD",
    "czech republic": "CZE", "czechia": "CZE",
    "south korea": "KOR", "north korea": "PRK",
    "united states of america": "USA", "usa": "USA",
    "viet nam": "VNM", "vietnam": "VNM",
    "bosnia and herzegovina": "BIH",
    "cabo verde": "CPV", "cape verde": "CPV",
    "moldova": "MDA", "republic of moldova": "MDA",
    "palestine": "PSE", "state of palestine": "PSE",
    "eswatini": "SWZ", "swaziland": "SWZ",
    "north macedonia": "MKD", "macedonia": "MKD",
    "myanmar": "MMR", "burma": "MMR",
    "ivory coast": "CIV", "côte d'ivoire": "CIV", "cote d'ivoire": "CIV",
    "timor-leste": "TLS", "east timor": "TLS",
    "the gambia": "GMB", "the bahamas": "BHS", "the netherlands": "NLD",
    "united kingdom": "GBR", "uk": "GBR",
    "vietnam": "VNM",
}


def geo_for(iso3: str):
    """Devuelve dict {name,lat,lon} para un código ISO3, o None."""
    if not iso3:
        return None
    iso3 = iso3.upper()
    alias = _ALIASES.get(iso3)
    if alias is not None:
        iso3 = alias
    return GEO.get(iso3)


def geo_by_name(name: str):
    if not name:
        return None
    return GEO.get(_NAME_FALLBACK.get(name.strip().lower(), "")) if name.strip().lower() in _NAME_FALLBACK else None


def match_country_by_name(name: str):
    """Resuelve un nombre de país (categoría RSS, texto libre) a su centroide."""
    if not name:
        return None
    s = name.strip().lower()
    if s in _NAME_FALLBACK:
        return GEO[_NAME_FALLBACK[s]]
    s2 = re.sub(r"\(.*?\)", "", s).strip()
    if s2 and s2 in _NAME_FALLBACK:
        return GEO[_NAME_FALLBACK[s2]]
    iso = _NAME_VARIANTS.get(s) or _NAME_VARIANTS.get(s2)
    if iso:
        return GEO.get(iso)
    return None
