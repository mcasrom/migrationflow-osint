import json
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
