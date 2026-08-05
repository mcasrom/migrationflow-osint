"""Colector UNHCR Refugee Data Finder — stock de refugiados/asilo/IDP por país."""
import asyncio
from datetime import datetime, timezone

import httpx

from src.config import (UNHCR_API, UNHCR_YEARS, UNHCR_PAGE_LIMIT,
                        UNHCR_COOLDOWN_MS, HTTP_TIMEOUT, USER_AGENT,
                        MIN_VALUE, severity_for)
from src.logging import get_logger
from src.models import Event, fmt_int
from src.collectors.base import BaseCollector
from src.collectors.countries import geo_for

logger = get_logger("src.collectors.unhcr")


def _num(v):
    """Convierte a int; '-' o vacío → 0."""
    if v is None or v == "-" or v == "":
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class UNHCRCollector(BaseCollector):
    name = "unhcr"
    source = "unhcr"

    async def _fetch_page(self, client: httpx.AsyncClient, params: dict) -> dict:
        resp = await client.get(f"{UNHCR_API}/population/", params=params)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_all(self, client: httpx.AsyncClient, params: dict) -> list[dict]:
        items: list[dict] = []
        page = 1
        max_pages = None
        while True:
            p = dict(params)
            p["page"] = page
            data = await self._fetch_page(client, p)
            items.extend(data.get("items", []))
            max_pages = int(data.get("maxPages") or 0)
            if page >= max_pages:
                break
            page += 1
            if UNHCR_COOLDOWN_MS:
                await asyncio.sleep(UNHCR_COOLDOWN_MS / 1000)
        return items

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            for year in UNHCR_YEARS:
                logger.info("[unhcr] año %d: consultando por origen (coo_all)...", year)
                coo_rows = await self._fetch_all(client, {
                    "year": year, "coo_all": "true",
                    "limit": UNHCR_PAGE_LIMIT,
                })
                logger.info("[unhcr] año %d: consultando por acogida (coa_all)...", year)
                coa_rows = await self._fetch_all(client, {
                    "year": year, "coa_all": "true",
                    "limit": UNHCR_PAGE_LIMIT,
                })

                for row in coo_rows:
                    iso = (row.get("coo_iso") or row.get("coo") or "").upper()
                    geo = geo_for(iso) if iso not in ("-", "") else None
                    if not geo or not iso:
                        continue
                    name = row.get("coo_name") or geo["name"]
                    refugees = _num(row.get("refugees"))
                    idps = _num(row.get("idps"))
                    if refugees >= MIN_VALUE["refugees_origin"]:
                        events.append(self._stock_event(
                            iso, name, year, "refugees_origin", refugees,
                            f"{fmt_int(refugees)} refugiados originarios de {name}",
                            row))
                    if idps >= MIN_VALUE["idp"]:
                        events.append(self._stock_event(
                            iso, name, year, "idp", idps,
                            f"{fmt_int(idps)} desplazados internos en {name}",
                            row))

                    asylum_origin = _num(row.get("asylum_seekers"))
                    ooc = _num(row.get("ooc"))
                    oip = _num(row.get("oip"))
                    if asylum_origin >= MIN_VALUE["asylum_origin"]:
                        events.append(self._stock_event(
                            iso, name, year, "asylum_origin", asylum_origin,
                            f"{fmt_int(asylum_origin)} solicitantes de asilo originarios de {name}",
                            row))
                    if ooc >= MIN_VALUE["ooc_origin"]:
                        events.append(self._stock_event(
                            iso, name, year, "ooc_origin", ooc,
                            f"{fmt_int(ooc)} otras personas de interés (OOC) originarias de {name}",
                            row))
                    if oip >= MIN_VALUE["oip_origin"]:
                        events.append(self._stock_event(
                            iso, name, year, "oip_origin", oip,
                            f"{fmt_int(oip)} personas en necesidad de protección internacional (OIP) originarias de {name}",
                            row))

                for row in coa_rows:
                    iso = (row.get("coa_iso") or row.get("coa") or "").upper()
                    geo = geo_for(iso) if iso not in ("-", "") else None
                    if not geo or not iso:
                        continue
                    name = row.get("coa_name") or geo["name"]
                    refugees = _num(row.get("refugees"))
                    asylum = _num(row.get("asylum_seekers"))
                    if refugees >= MIN_VALUE["refugees"]:
                        events.append(self._stock_event(
                            iso, name, year, "refugees", refugees,
                            f"{fmt_int(refugees)} refugiados acogidos en {name}",
                            row))
                    if asylum >= MIN_VALUE["asylum"]:
                        events.append(self._stock_event(
                            iso, name, year, "asylum", asylum,
                            f"{fmt_int(asylum)} solicitantes de asilo en {name}",
                            row))
        return events

    def _stock_event(self, iso: str, name: str, year: int, event_type: str,
                     value: int, title: str, row: dict) -> Event:
        geo = geo_for(iso)
        desc = (
            f"Dato anual {year} · {fmt_int(value)} personas.\n"
            f"Fuente: UNHCR Refugee Data Finder (api.unhcr.org)."
        )
        return Event(
            source=self.source,
            source_id=f"unhcr:{year}:{iso}:{event_type}",
            event_type=event_type,
            lat=geo["lat"],
            lon=geo["lon"],
            level=severity_for(event_type, value),
            title=title,
            description=desc,
            country=name,
            iso3=iso,
            category="stock",
            admin_level="admin0",
            value=float(value),
            value_type=event_type,
            reported_at=f"{year}-12-31T00:00:00Z",
            raw_json={"year": year, "coo": row.get("coo"), "coa": row.get("coa")},
        )
