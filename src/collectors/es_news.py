"""Colector de prensa española — migración y fronteras de España.

Lee RSS de medios nacionales + LOCALES de Ceuta/Melilla + búsquedas de Google
News para captar noticias de migración que ReliefWeb no cubre: asalto a la
valla de Ceuta/Melilla, desembarcos, pateras, crisis migratoria española.
Geolocaliza cada noticia a su zona (Ceuta, Melilla, Almería, Canarias...).

Reforzado 2026-09-02:
- Añadidos feeds locales (El Faro de Ceuta, Ceuta TV, Melilla Hoy).
- Añadidas búsquedas Google News por keyword (cubre Ceuta/Melilla/frontera).
- Subido el límite de items leídos por feed (30 → 60).
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from src.config import HTTP_TIMEOUT, USER_AGENT
from src.logging import get_logger
from src.models import Event
from src.collectors.base import BaseCollector

logger = get_logger("src.collectors.es_news")

# Feeds RSS: nacionales + locales de la frontera sur
FEEDS = [
    ("europapress", "https://www.europapress.es/rss/rss.aspx?ch=1"),
    ("elpais", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
    ("elfarodeceuta", "https://elfarodeceuta.com/feed/"),
    ("ceutatv", "https://ceutatv.com/feed/"),
    ("melillahoy", "https://www.melillahoy.es/rss"),
]

MAX_ITEMS_PER_FEED = 60

# Búsquedas de Google News (RSS) para no depender solo de portadas
GN_QUERIES = [
    "Ceuta valla asalto migración",
    "Ceuta Melilla frontera migrantes",
    "patera desembarco inmigración España",
    "cayuco Canarias llegada",
]

# Búsquedas HISTÓRICAS dirigidas: crisis del asalto a la valla de Ceuta
# (julio 2026). Google News indexa por fecha de publicación real, lo que
# permite recuperar retrospectivamente el periodo que los RSS ya no tienen.
GN_BACKFILL_QUERIES = [
    '"asalto a la valla de Ceuta" 2026',
    '"70.000" Ceuta frontera',
    'Ceuta asalto valla julio',
    'Ceuta crisis migratoria asalto',
]

# Ventana de captura histórica: solo eventos >= esta fecha (el asalto real fue ~30-jul)
BACKFILL_SINCE = "2026-07-25"

# Keywords de migración/fronteras españolas
ES_KEYWORDS = [
    "ceuta", "melilla", "valla", "patera", "desembarco", "inmigraci",
    "crisis migratoria", "cayuco", "salvamento marítimo", "marruecos",
    "cartagena", "almería", "almeria", "cádiz", "cadiz", "estrecho",
    "frontera", "migrantes", "menas", "ciudad autónoma", "asalt",
]

# Zonas → coordenadas (aproximadas, para geolocalizar la noticia en España)
ZONES = {
    "ceuta": (35.8894, -5.3212, "Ceuta"),
    "melilla": (35.2923, -2.9381, "Melilla"),
    "cartagena": (37.6051, -0.9862, "Cartagena"),
    "almería": (36.8340, -2.4637, "Almería"),
    "almeria": (36.8340, -2.4637, "Almería"),
    "cádiz": (36.5271, -6.2886, "Cádiz"),
    "cadiz": (36.5271, -6.2886, "Cádiz"),
    "estrecho": (35.96, -5.6, "Estrecho de Gibraltar"),
    "frontera": (35.3, -5.1, "Frontera sur de España"),
    "canarias": (28.5, -15.4, "Islas Canarias"),
    "granada": (37.1773, -3.5986, "Granada"),
    "málaga": (36.7213, -4.4214, "Málaga"),
    "malaga": (36.7213, -4.4214, "Málaga"),
}

DEFAULT_ES_COORD = (40.4168, -3.7038)  # Madrid, fallback


def _clean(t):
    if not t:
        return ""
    return re.sub(r"<[^>]+>", "", t).strip()


def _geo(title, desc):
    """Asigna coordenadas + etiqueta según la zona mencionada."""
    hay = f"{title} {desc}".lower()
    for kw, (zlat, zlon, zname) in ZONES.items():
        if kw in hay:
            return zlat, zlon, zname
    return DEFAULT_ES_COORD[0], DEFAULT_ES_COORD[1], "España"


def _mk_event(feed_name, title, description, link, guid, pub):
    lat, lon, label = _geo(title, description)
    return Event(
        source="es_news",
        source_id=f"es_news:{feed_name}:{guid[:70]}",
        event_type="news",
        lat=lat,
        lon=lon,
        level="info",
        title=(title or "Migración España")[:300],
        description=(description[:500] + ("…" if len(description) > 500 else "")) or "",
        country=label,
        iso3="ESP",
        category="news",
        admin_level="incident",
        reported_at=pub,
        raw_json={"url": link, "source": feed_name},
    )


class ESNewsCollector(BaseCollector):
    name = "es_news"
    source = "es_news"

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {
            "User-Agent": USER_AGENT or ("Mozilla/5.0 MigrationFlow"),
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers, follow_redirects=True) as client:
            # ---- 1) RSS de medios (nacionales + locales) ----
            for feed_name, url in FEEDS:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning("[es_news] %s HTTP %s", feed_name, resp.status_code)
                        continue
                    root = ET.fromstring(resp.content)
                    items = root.findall("channel/item") or root.findall(".//item")
                    for item in items[:MAX_ITEMS_PER_FEED]:
                        title = _clean(item.findtext("title"))
                        description = _clean(item.findtext("description"))
                        link = (item.findtext("link") or "").strip()
                        guid = item.findtext("guid") or link
                        hay = f"{title} {description}".lower()
                        if not any(kw in hay for kw in ES_KEYWORDS):
                            continue
                        pub = None
                        try:
                            dt = parsedate_to_datetime(item.findtext("pubDate") or "")
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            pub = dt.isoformat()
                        except (TypeError, ValueError):
                            pass
                        events.append(_mk_event(feed_name, title, description, link, guid, pub))
                except Exception as e:
                    logger.error("[es_news] %s error: %s", feed_name, e)

            # ---- 2) Búsquedas Google News (cubre lo que no está en portadas) ----
            for q in GN_QUERIES:
                try:
                    url = ("https://news.google.com/rss/search?q="
                           + urllib.parse.quote(q) + "&hl=es&gl=ES&ceid=ES:es")
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    root = ET.fromstring(resp.content)
                    items = root.findall("channel/item") or root.findall(".//item")
                    for item in items[:40]:
                        title = _clean(item.findtext("title"))
                        link = (item.findtext("link") or "").strip()
                        guid = item.findtext("guid") or link
                        pub = None
                        try:
                            dt = parsedate_to_datetime(item.findtext("pubDate") or "")
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            pub = dt.isoformat()
                        except (TypeError, ValueError):
                            pass
                        events.append(_mk_event("google-news:" + q[:20], title, "",
                                                link, guid, pub))
                except Exception as e:
                    logger.error("[es_news] google-news %s error: %s", q, e)

            # ---- 3) Búsquedas HISTÓRICAS del asalto (recupera julio-agosto) ----
            for q in GN_BACKFILL_QUERIES:
                try:
                    url = ("https://news.google.com/rss/search?q="
                           + urllib.parse.quote(q) + "&hl=es&gl=ES&ceid=ES:es")
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    root = ET.fromstring(resp.content)
                    items = root.findall("channel/item") or root.findall(".//item")
                    for item in items[:60]:
                        title = _clean(item.findtext("title"))
                        link = (item.findtext("link") or "").strip()
                        guid = item.findtext("guid") or link
                        pub = None
                        try:
                            dt = parsedate_to_datetime(item.findtext("pubDate") or "")
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            pub = dt.isoformat()
                        except (TypeError, ValueError):
                            pass
                        # solo eventos dentro de la ventana histórica del asalto
                        if pub:
                            try:
                                pdt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                if pdt < datetime.fromisoformat(BACKFILL_SINCE).replace(tzinfo=timezone.utc):
                                    continue
                            except (TypeError, ValueError):
                                pass
                        events.append(_mk_event("google-news-hist:" + q[:16], title, "",
                                                link, guid, pub))
                except Exception as e:
                    logger.error("[es_news] google-news-hist %s error: %s", q, e)

        # dedupe por source_id manteniendo el primero
        seen = set()
        uniq = []
        for ev in events:
            if ev.source_id in seen:
                continue
            seen.add(ev.source_id)
            uniq.append(ev)
        logger.info("[es_news] %d noticias de migración en España (tras dedupe)", len(uniq))
        return uniq
