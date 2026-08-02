"""Colector IOM DTM — stock global de desplazados internos por país (HDX, CSV semanal)."""
import csv
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.config import (HDX_DTM_URL, HTTP_TIMEOUT, USER_AGENT,
                        MIN_VALUE, severity_for, DTM_ADMIN_LEVELS)
from src.logging import get_logger
from src.models import Event, fmt_int
from src.collectors.base import BaseCollector
from src.collectors.countries import geo_for, geo_by_name

logger = get_logger("src.collectors.iom_dtm")

_CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "dtm_latest.csv"


def _num(v):
    if v is None or v == "" or v == "-":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class IOMDTMCollector(BaseCollector):
    name = "iom_dtm"
    source = "iom_dtm"

    async def _download(self, client: httpx.AsyncClient) -> Path:
        logger.info("[iom_dtm] descargando CSV (37 MB)...")
        async with client.stream("GET", HDX_DTM_URL, follow_redirects=True) as r:
            r.raise_for_status()
            with open(_CACHE, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
        logger.info("[iom_dtm] CSV descargado (%d MB)", _CACHE.stat().st_size // (1 << 20))
        return _CACHE

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            path = await self._download(client)

        # Última ronda (reportingDate) por país admin0
        latest: dict[str, dict] = {}
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("adminLevel") not in DTM_ADMIN_LEVELS:
                    continue
                pcode = (row.get("admin0Pcode") or "").strip().upper()
                if not pcode:
                    continue
                rdate = (row.get("reportingDate") or "").strip()[:10]
                cur = latest.get(pcode)
                if cur is None or rdate > cur["reportingDate"]:
                    latest[pcode] = {"reportingDate": rdate, "row": row}

        for pcode, entry in latest.items():
            row = entry["row"]
            value = _num(row.get("numPresentIdpInd"))
            if value is None or value < MIN_VALUE["dtm_idp"]:
                continue
            geo = geo_for(pcode) or geo_by_name(row.get("admin0Name") or "")
            if not geo:
                logger.info("[iom_dtm] sin geolocalización para %s (%s)",
                            pcode, row.get("admin0Name"))
                continue
            name = row.get("admin0Name") or geo["name"]
            op = row.get("operation") or ""
            reason = row.get("displacementReason") or ""
            reported = entry["reportingDate"]
            events.append(Event(
                source=self.source,
                source_id=f"iom_dtm:{pcode}:{reported}",
                event_type="dtm_idp",
                lat=geo["lat"],
                lon=geo["lon"],
                level=severity_for("dtm_idp", value),
                title=f"{fmt_int(value)} desplazados internos en {name}",
                description=(
                    f"Stock de IDP estimado: {fmt_int(value)} personas (ronda {row.get('roundNumber') or '-'}, "
                    f"{reported}).\nOperación DTM: {op}. Razón: {reason or 'no especificada'}.\n"
                    "Fuente: IOM DTM vía HDX (data.humdata.org)."),
                country=name,
                iso3=pcode,
                category="stock",
                admin_level="admin0",
                value=float(value),
                value_type="dtm_idp",
                reported_at=f"{reported}Z",
                raw_json={"operation": op, "round": row.get("roundNumber"),
                          "reason": reason},
            ))
        return events
