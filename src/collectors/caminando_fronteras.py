"""Colector Caminando Fronteras — víctimas en las rutas hacia el Estado español.

Fuente: web pública de la ONG (sin API). El colector hace scraping curado:
1. Localiza el último informe del "Monitoreo del Derecho a la Vida" vía el RSS
   de búsqueda del sitio.
2. Descarga el post y parsea las cifras por ruta (Atlántica, Argelia, Estrecho,
   Alborán, Terrestre) y el total.

Mecanismo de respaldo: si existe `data/cf_override.json`, se usan esas cifras
(curated) en lugar del parseo automático. Si algo falla, se conservan los datos
anteriores (expiran solos por TTL) y se registra el error.

Nota metodológica: Caminando Fronteras es una *estimación* de la ONG que incluye
personas fallecidas y desaparecidas (embarcaciones sin confirmación); no es
comparable 1:1 con IOM MMP (solo incidentes confirmados). Se muestra como
fuente complementaria con su metodología explícita.
"""
import json
import re
import calendar
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from src.config import (CF_RSS_SEARCH, CF_MONITOREO_PREFIX, HTTP_TIMEOUT,
                        severity_for)
from src.logging import get_logger
from src.models import Event, fmt_int
from src.collectors.base import BaseCollector
from src import db

logger = get_logger("src.collectors.caminando_fronteras")

_OVERRIDE = Path(__file__).resolve().parent.parent.parent / "data" / "cf_override.json"

# key: (iso3, nombre ES, lat, lon)
ROUTES = {
    "atlantica": ("CF_ATL", "Ruta atlántica (Canarias)", 22.5, -18.0),
    "argelia": ("CF_ARG", "Ruta argelina (Mediterráneo occidental)", 36.2, -1.5),
    "estrecho": ("CF_EST", "Ruta del Estrecho (nado a Ceuta)", 35.9, -5.6),
    "alboran": ("CF_ALB", "Ruta de Alborán", 35.8, -3.0),
    "terrestre": ("CF_TER", "Ruta terrestre (valla de Ceuta)", 35.89, -5.31),
}

_ES_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _num(v) -> int:
    if v is None:
        return 0
    try:
        return int(str(v).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0


def _clean_html(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text)


def _month_end(year: int, month: int) -> str:
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}T00:00:00Z"


def _period_from_title(title: str) -> tuple[str, str]:
    """Devuelve (periodo_humano, reported_at) a partir del título del informe."""
    m = re.search(r"(?:primeros?|primero)\s+(\d{1,2})\s+meses?\s+(20\d\d)", title, re.I)
    if m:
        n, year = int(m.group(1)), int(m.group(2))
        return f"{year}, primeros {n} meses", _month_end(year, n)
    m = re.search(r"(20\d\d)", title)
    if m:
        year = int(m.group(1))
        return str(year), f"{year}-12-31T00:00:00Z"
    return "", None


def _parse_report(title: str, text: str) -> dict:
    """Parsea las cifras del informe. Lanza ValueError si el total no se encuentra."""
    period, reported = _period_from_title(title)
    total = _num(re.search(r"([\d.]+)\s+personas han muerto", text, re.I).group(1)) \
        if re.search(r"([\d.]+)\s+personas han muerto", text, re.I) else 0
    if not total:
        m = re.search(r"han fallecido\s+([\d.]+)\s+personas", text, re.I)
        total = _num(m.group(1)) if m else 0
    if not total:
        raise ValueError("no se encontró el total de víctimas")

    routes: dict[str, int] = {}
    for key in ROUTES:
        routes[key] = 0

    m = re.search(r"ruta atl[áa]ntica[^.]*?con\s+([\d.]+)\s+v[ií]ctimas", text, re.I)
    if m: routes["atlantica"] = _num(m.group(1))
    m = re.search(r"ruta argelina[^.]*?(?:las|la)\s+([\d.]+)\s+v[ií]ctimas", text, re.I)
    if m: routes["argelia"] = _num(m.group(1))
    m = re.search(r"ruta del Estrecho[^.]*?pasando de [\d.]+ a ([\d.]+)", text, re.I)
    if m: routes["estrecho"] = _num(m.group(1))
    m = re.search(r"valla de Ceuta[^.]*?muerte de ([\d.]+) personas", text, re.I)
    if m: routes["terrestre"] = _num(m.group(1))
    m = re.search(r"registrado\s+([\d.]+)\s+personas fallecidas", text, re.I)
    if m: routes["alboran"] = _num(m.group(1))

    return {
        "period": period, "reported_at": reported, "total": total,
        "routes": routes,
    }


class CaminandoFronterasCollector(BaseCollector):
    name = "caminando_fronteras"
    source = "caminando_fronteras"

    async def collect(self) -> list[Event]:
        report = None
        url = ""
        headers = {"User-Agent": _UA}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            # 1) Último informe vía RSS de búsqueda
            rss = await client.get(CF_RSS_SEARCH)
            rss.raise_for_status()
            root = ET.fromstring(rss.content)
            items = []
            for item in root.iter("item"):
                link = (item.findtext("link") or "").strip()
                if CF_MONITOREO_PREFIX in link:
                    items.append((item.findtext("title") or "", link,
                                  item.findtext("pubDate") or ""))
            if not items:
                raise RuntimeError("no se encontró ningún informe en el RSS")
            title, url, pub = items[0]

            # 2) Override curado si existe
            if _OVERRIDE.exists():
                try:
                    over = json.loads(_OVERRIDE.read_text(encoding="utf-8"))
                    d = over.get("data", {})
                    if d.get("routes") and d.get("total"):
                        report = {
                            "period": d.get("period") or _period_from_title(title)[0],
                            "reported_at": d.get("reported_at")
                                          or _period_from_title(title)[1],
                            "total": _num(d.get("total")),
                            "routes": {k: _num(v) for k, v in d["routes"].items()},
                        }
                        url = d.get("url") or url
                        logger.info("[caminando_fronteras] usando override curado (%s)",
                                    title)
                except Exception as e:
                    logger.warning("[caminando_fronteras] override inválido: %s", e)

            # 3) Si no hay override, parsear el HTML del post
            if report is None:
                post = await client.get(url)
                post.raise_for_status()
                text = _clean_html(post.text)
                if 'class="entry-content"' in post.text:
                    m = re.search(r'class="entry-content"[^>]*>(.*)', post.text, re.S)
                    if m:
                        text = _clean_html(m.group(1))
                report = _parse_report(title, text)
                logger.info("[caminando_fronteras] informe parseado: %s", title)

        if not report.get("reported_at"):
            raise ValueError("no se pudo determinar el periodo del informe")

        # Nuevo informe: expira el anterior para no duplicar víctimas en el mapa.
        try:
            db.expire_source_type(self.source, "cf_victims")
        except Exception as e:
            logger.warning("[caminando_fronteras] no se pudo expirar el informe previo: %s", e)

        events: list[Event] = []
        for key, (iso3, label, lat, lon) in ROUTES.items():
            n = report["routes"].get(key, 0)
            if n <= 0:
                continue
            events.append(Event(
                source=self.source,
                source_id=f"cf:{report['reported_at'][:10]}:{key}",
                event_type="cf_victims",
                lat=lat,
                lon=lon,
                level=severity_for("cf_victims", n),
                title=f"{fmt_int(n)} víctimas en {label}",
                description=(
                    f"Caminando Fronteras · Monitoreo del Derecho a la Vida "
                    f"({report['period']}): {fmt_int(n)} víctimas en {label}.\n"
                    "Estimación del colectivo que incluye personas fallecidas y "
                    "desaparecidas; no es comparable 1:1 con IOM MMP (solo "
                    "incidentes confirmados).\n"
                    f"Total del periodo: {fmt_int(report['total'])} víctimas.\n"
                    f"Fuente: {url}"),
                country=label,
                iso3=iso3,
                category="incident",
                admin_level="route",
                value=float(n),
                value_type="victims",
                reported_at=report["reported_at"],
                raw_json={"period": report["period"], "total": report["total"],
                          "url": url},
            ))
        return events
