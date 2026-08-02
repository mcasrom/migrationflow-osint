"""Colector Missing Migrants Project (IOM) — incidentes con muertos/desaparecidos."""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from src.config import (HDX_MMP_URL, HTTP_TIMEOUT, USER_AGENT,
                        MMP_RETENTION_MONTHS, severity_for)
from src.logging import get_logger
from src.models import Event, fmt_int
from src.collectors.base import BaseCollector

logger = get_logger("src.collectors.missing_migrants")

_CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "mmp_latest.csv"


def _num(v):
    if v is None or v == "" or v == "-":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _parse_coords(text: str):
    if not text:
        return None
    try:
        lat_s, lon_s = text.split(",", 1)
        lat = float(lat_s.strip())
        lon = float(lon_s.strip())
        if abs(lat) <= 90 and abs(lon) <= 180:
            return lat, lon
    except (ValueError, TypeError):
        pass
    return None


class MissingMigrantsCollector(BaseCollector):
    name = "missing_migrants"
    source = "missing_migrants"

    async def _download(self, client: httpx.AsyncClient) -> Path:
        logger.info("[missing_migrants] descargando CSV (7 MB)...")
        async with client.stream("GET", HDX_MMP_URL, follow_redirects=True) as r:
            r.raise_for_status()
            with open(_CACHE, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
        return _CACHE

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {"User-Agent": USER_AGENT}
        cutoff = datetime.now(timezone.utc) - timedelta(days=MMP_RETENTION_MONTHS * 30)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            path = await self._download(client)

        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_s = (row.get("reported_date") or "").strip()
                if not date_s:
                    continue
                try:
                    date = datetime.fromisoformat(date_s).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if date < cutoff:
                    continue
                coords = _parse_coords(row.get("location_coodinates"))
                if not coords:
                    continue
                lat, lon = coords
                dead = _num(row.get("number_dead"))
                missing = _num(row.get("number_missing"))
                total = _num(row.get("total_dead_and_missing")) or (dead + missing)
                if total <= 0:
                    continue
                country = row.get("country_of_incident") or "Desconocido"
                route = row.get("migration_route") or ""
                cause = row.get("cause_death") or "Causa no especificada"
                src_name = row.get("information_source") or ""
                url = row.get("url") or ""
                expires = (date + timedelta(days=MMP_RETENTION_MONTHS * 30)).isoformat()
                desc = (f"{fmt_int(total)} personas: {fmt_int(dead)} muertas, {fmt_int(missing)} desaparecidas. "
                        f"\nFecha: {date_s}. Causa: {cause}."
                        + (f"\nRuta: {route}." if route else "")
                        + (f"\nFuente: {src_name}." if src_name else ""))
                if url and url.startswith("http"):
                    desc += f"\n{url}"
                events.append(Event(
                    source=self.source,
                    source_id=f"mmp:{row.get('web_id')}",
                    event_type="missing",
                    lat=lat,
                    lon=lon,
                    level=severity_for("missing", total),
                    title=f"{fmt_int(total)} muertos y desaparecidos en {country}",
                    description=desc,
                    country=country,
                    iso3="",
                    category="incident",
                    admin_level="incident",
                    value=float(total),
                    value_type="total_dead_and_missing",
                    reported_at=f"{date_s}T00:00:00Z",
                    expires_at=expires,
                    raw_json={"route": route, "cause": cause, "source": src_name},
                ))
        logger.info("[missing_migrants] %d incidentes recientes con coordenadas", len(events))
        return events
