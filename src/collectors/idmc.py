"""Colector IDMC (desplazamiento por conflicto) vía la API de UNHCR."""
import asyncio

import httpx

from src.config import (UNHCR_API, UNHCR_YEARS, UNHCR_PAGE_LIMIT,
                        UNHCR_COOLDOWN_MS, HTTP_TIMEOUT, USER_AGENT,
                        MIN_VALUE, severity_for)
from src.logging import get_logger
from src.models import Event, fmt_int
from src.collectors.base import BaseCollector
from src.collectors.countries import geo_for

logger = get_logger("src.collectors.idmc")


def _num(v):
    if v is None or v == "-" or v == "":
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class IDMCCollector(BaseCollector):
    name = "idmc"
    source = "idmc"

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            for year in UNHCR_YEARS:
                page = 1
                max_pages = None
                while True:
                    resp = await client.get(f"{UNHCR_API}/idmc/", params={
                        "year": year, "coo_all": "true",
                        "limit": UNHCR_PAGE_LIMIT, "page": page,
                    })
                    resp.raise_for_status()
                    data = resp.json()
                    for row in data.get("items", []):
                        iso = (row.get("coo_iso") or row.get("coo") or "").upper()
                        geo = geo_for(iso) if iso not in ("-", "") else None
                        total = _num(row.get("total"))
                        if not geo or not iso or total < MIN_VALUE["displacement"]:
                            continue
                        name = row.get("coo_name") or geo["name"]
                        events.append(Event(
                            source=self.source,
                            source_id=f"idmc:{year}:{iso}",
                            event_type="displacement",
                            lat=geo["lat"],
                            lon=geo["lon"],
                            level=severity_for("displacement", total),
                            title=f"{year}: {fmt_int(total)} desplazados por conflicto en {name}",
                            description=(
                                f"Dato anual {year} · {fmt_int(total)} personas desplazadas "
                                f"por conflicto o violencia en {name}.\n"
                                "Fuente: IDMC vía UNHCR (api.unhcr.org)."),
                            country=name,
                            iso3=iso,
                            category="stock",
                            admin_level="admin0",
                            value=float(total),
                            value_type="displacement",
                            reported_at=f"{year}-12-31T00:00:00Z",
                            raw_json={"year": year},
                        ))
                    max_pages = int(data.get("maxPages") or 0)
                    if page >= max_pages:
                        break
                    page += 1
                    if UNHCR_COOLDOWN_MS:
                        await asyncio.sleep(UNHCR_COOLDOWN_MS / 1000)
        return events
