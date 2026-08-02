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
    "democratic people's republic of korea": "PRK",
    "republic of korea": "KOR",
    "united republic of tanzania": "TZA",
    "tanzania": "TZA",
    "united kingdom of great britain and northern ireland": "GBR",
    "china, hong kong special administrative region": "HKG",
    "hong kong": "HKG",
    "macedonia (the former yugoslav republic of)": "MKD",
}

_ENTITY_RE = re.compile(r"&#0*39;|&#x27;", re.IGNORECASE)


def _clean_name(name: str) -> str:
    """Normaliza un nombre de país: entidades HTML, espacios, paréntesis."""
    s = name.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = _ENTITY_RE.sub("'", s)
    return re.sub(r"\s+", " ", s.strip()).lower()


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
    s = _clean_name(name)
    if s in _NAME_FALLBACK:
        iso = _NAME_FALLBACK[s]
        return {**GEO[iso], "iso3": iso}
    s2 = re.sub(r"\(.*?\)", "", s).strip()
    if s2 and s2 in _NAME_FALLBACK:
        iso = _NAME_FALLBACK[s2]
        return {**GEO[iso], "iso3": iso}
    iso = _NAME_VARIANTS.get(s) or _NAME_VARIANTS.get(s2)
    if iso and iso in GEO:
        return {**GEO[iso], "iso3": iso}
    return None


def match_country_iso3(name: str):
    """Devuelve el código ISO3 para un nombre de país, o None."""
    geo = match_country_by_name(name)
    return geo["iso3"] if geo else None
