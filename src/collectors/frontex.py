"""Colector Frontex — detecciones de cruces irregulares de frontera (IBC).

Fuente pública: ArcGIS FeatureServer de Frontex (sin API key).
- Capa de países de origen (1): detecciones mensuales por país (campos fYYYY_MM).
- Capa de rutas (0): total del mes actual por ruta + top nacionalidades.

Se ingesta:
- `arrivals`: total anual por país de origen (años completos + parcial actual).
- `arrivals_route`: total mensual por ruta migratoria (dato más reciente).

Nota metodológica: Frontex cuenta *detecciones* (una persona puede cruzarse
varias veces y, por tanto, contarse varias veces); son entradas irregulares,
complementarias a las víctimas de IOM MMP / Caminando Fronteras.
"""
import calendar
import re

import httpx

from src.config import (FRONTEX_SERVER, FRONTEX_COUNTRIES_LAYER,
                        FRONTEX_ROUTES_LAYER, FRONTEX_YEARS_BACK,
                        FRONTEX_MIN_ROUTE_TOTAL, HTTP_TIMEOUT, USER_AGENT,
                        MIN_VALUE, severity_for)
from src.logging import get_logger
from src.models import Event, fmt_int
from src.collectors.base import BaseCollector
from src.collectors.countries import geo_for

logger = get_logger("src.collectors.frontex")

_MONTH_RE = re.compile(r"^f(20\d\d)_(\d\d)$")

# Clave interna (se guarda en iso3), nombre ES y punto representativo por ruta.
ROUTE_META = {
    "western african": ("ROUTE_WAF", "Ruta atlántica (Canarias)", 22.5, -18.0),
    "western mediterranean": ("ROUTE_WMED", "Mediterráneo occidental (España)", 35.9, -2.5),
    "central mediterranean": ("ROUTE_CMED", "Mediterráneo central (Italia)", 35.5, 13.5),
    "eastern mediterranean": ("ROUTE_EMED", "Mediterráneo oriental (Grecia)", 35.5, 26.0),
    "eastern land borders": ("ROUTE_ELB", "Frontera terrestre oriental", 52.0, 23.0),
    "western balkan": ("ROUTE_WBAL", "Ruta de los Balcanes", 44.5, 20.5),
}


def _num(v):
    if v is None or v == "" or v == "-":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _month_end(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-{last:02d}T00:00:00Z"


def _discover_months(attrs: dict) -> dict:
    """Devuelve {año: [(mes, campo), ...]} a partir de los campos fYYYY_MM."""
    years: dict[int, list] = {}
    for k, v in attrs.items():
        m = _MONTH_RE.match(k)
        if m and v is not None:
            years.setdefault(int(m.group(1)), []).append((int(m.group(2)), k))
    for y in years:
        years[y].sort()
    return years


def _years_to_ingest(months: dict) -> list[tuple[int, list]]:
    """Años a ingestar: años completos recientes + el parcial en curso."""
    years = sorted(months)
    if not years:
        return []
    partial_year = years[-1]
    out = []
    for y in reversed(years[:-1]):
        if len(months[y]) == 12 and len(out) < FRONTEX_YEARS_BACK:
            out.append((y, months[y]))
    out.append((partial_year, months[partial_year]))  # siempre el parcial actual
    out.reverse()
    return out


class FrontexCollector(BaseCollector):
    name = "frontex"
    source = "frontex"

    async def _get(self, client: httpx.AsyncClient, layer: int,
                   limit: int = 2000) -> list[dict]:
        url = f"{FRONTEX_SERVER}/{layer}/query"
        resp = await client.get(url, params={
            "f": "json", "where": "1=1", "outFields": "*",
            "returnGeometry": "false", "resultRecordCount": str(limit),
        })
        resp.raise_for_status()
        data = resp.json()
        return data.get("features", [])

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            countries = await self._get(client, FRONTEX_COUNTRIES_LAYER)
            routes = await self._get(client, FRONTEX_ROUTES_LAYER)

        events.extend(self._country_events(countries))
        events.extend(self._route_events(routes))
        logger.info("[frontex] %d eventos (%d países, %d rutas)",
                    len(events), len(countries), len(routes))
        return events

    def _country_events(self, features: list[dict]) -> list[Event]:
        events: list[Event] = []
        for feat in features:
            attrs = feat.get("attributes") or {}
            iso3 = (attrs.get("ISO3_CODE") or "").strip().upper()
            geo = geo_for(iso3)
            if not geo:
                continue
            months = _discover_months(attrs)
            if not months:
                continue
            name = attrs.get("NAME_ENGL") or attrs.get("CNTR_NAME") or geo["name"]
            for year, month_fields in _years_to_ingest(months):
                total = sum(_num(attrs.get(f)) for _, f in month_fields)
                if total < MIN_VALUE["arrivals"]:
                    continue
                if len(month_fields) == 12:
                    reported = f"{year}-12-31T00:00:00Z"
                    periodo = f"año {year}"
                else:
                    last_mm = max(mm for mm, _ in month_fields)
                    reported = _month_end(year, last_mm)
                    periodo = f"{year} (enero–{last_mm:02d}, dato parcial)"
                events.append(Event(
                    source=self.source,
                    source_id=f"frontex:{year}:{iso3}",
                    event_type="arrivals",
                    lat=geo["lat"],
                    lon=geo["lon"],
                    level=severity_for("arrivals", total),
                    title=f"{periodo}: {fmt_int(total)} entradas irregulares desde {name}",
                    description=(
                        f"Frontex · detecciones de cruces irregulares de frontera (IBC) "
                        f"{periodo} desde {name}: {fmt_int(total)}.\n"
                        "Nota: Frontex cuenta *detecciones*; una persona puede cruzar "
                        "varias veces y contarse varias veces."),
                    country=name,
                    iso3=iso3,
                    category="stock",
                    admin_level="admin0",
                    value=float(total),
                    value_type="detections",
                    reported_at=reported,
                    raw_json={"year": year, "months": len(month_fields)},
                ))
        return events

    def _route_events(self, features: list[dict]) -> list[Event]:
        events: list[Event] = []
        for feat in features:
            attrs = feat.get("attributes") or {}
            rname = (attrs.get("Name") or "").strip().lower()
            meta = next((v for k, v in ROUTE_META.items() if k in rname), None)
            if not meta:
                continue
            key, label, lat, lon = meta
            total = _num(attrs.get("TotalNumber") or attrs.get("Total"))
            if total < FRONTEX_MIN_ROUTE_TOTAL:
                continue
            period = (attrs.get("Period") or "").strip()   # p. ej. "June 2026"
            year = _num(attrs.get("Year"))
            month = 0
            for i, mname in enumerate(["January", "February", "March", "April", "May",
                                       "June", "July", "August", "September", "October",
                                       "November", "December"]):
                if mname.lower() in period.lower():
                    month = i + 1
                    break
            if not (year and month):
                continue
            nat1 = (attrs.get("Nat1") or "").strip()
            nat2 = (attrs.get("Nat2") or "").strip()
            nats = " · ".join(x for x in [nat1, nat2] if x)
            reported = _month_end(int(year), month)
            m = month + 2                                  # expira ~2 meses tras el mes
            ey = int(year) + (m - 1) // 12
            em = (m - 1) % 12 + 1
            expires = _month_end(ey, em)
            events.append(Event(
                source=self.source,
                source_id=f"frontex:route:{key}:{year}-{month:02d}",
                event_type="arrivals_route",
                lat=lat,
                lon=lon,
                level=severity_for("arrivals_route", total),
                title=f"{fmt_int(total)} entradas irregulares este mes ({label})",
                description=(
                    f"Frontex · detecciones de cruces irregulares de frontera "
                    f"en {label} durante {period}: {fmt_int(total)}."
                    + (f"\nPrincipales nacionalidades: {nats}." if nats else "")
                    + "\nNota: Frontex cuenta *detecciones*; puede incluir a la misma "
                      "persona varias veces."),
                country=label,
                iso3=key,
                category="stock",
                admin_level="route",
                value=float(total),
                value_type="detections",
                reported_at=reported,
                expires_at=expires,
                raw_json={"route": key, "period": period, "nationalities": nats},
            ))
        return events
