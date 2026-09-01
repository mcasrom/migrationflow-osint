"""Colector de prensa española — migración y fronteras de España.

Lee RSS de Europa Press nacional y El País para captar noticias de migración
que ReliefWeb no cubre: asalto a la valla de Ceuta/Melilla, desembarcos
(Cartagena, Almería, Cádiz...), pateras, crisis migratoria española.
Geolocaliza a España con coordenadas aproximadas de la zona.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from src.config import HTTP_TIMEOUT, USER_AGENT
from src.logging import get_logger
from src.models import Event
from src.collectors.base import BaseCollector

logger = get_logger("src.collectors.es_news")

FEEDS = [
    ("europapress", "https://www.europapress.es/rss/rss.aspx?ch=1"),
    ("elpais", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
]

# Keywords de migración/fronteras españolas
ES_KEYWORDS = [
    "ceuta", "melilla", "valla", "patera", "desembarco", "inmigraci",
    "crisis migratoria", "cayuco", "salvamento marítimo", "marruecos",
    "cartagena", "almería", "almeria", "cádiz", "cadiz", "estrecho",
    "frontera", "migrantes", "menas", "ciudad autónoma",
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


class ESNewsCollector(BaseCollector):
    name = "es_news"
    source = "es_news"

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {
            "User-Agent": USER_AGENT or ("Mozilla/5.0 MigrationFlow"),
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            for feed_name, url in FEEDS:
                try:
                    resp = await client.get(url, follow_redirects=True)
                    if resp.status_code != 200:
                        logger.warning("[es_news] %s HTTP %s", feed_name, resp.status_code)
                        continue
                    root = ET.fromstring(resp.content)
                    items = root.findall("channel/item") or root.findall(".//item")
                    for item in items[:30]:
                        title = _clean(item.findtext("title"))
                        description = _clean(item.findtext("description"))
                        link = (item.findtext("link") or "").strip()
                        guid = item.findtext("guid") or link
                        hay = f"{title} {description}".lower()
                        if not any(kw in hay for kw in ES_KEYWORDS):
                            continue
                        lat, lon, label = DEFAULT_ES_COORD[0], DEFAULT_ES_COORD[1], "España"
                        for kw, (zlat, zlon, zname) in ZONES.items():
                            if kw in hay:
                                lat, lon, label = zlat, zlon, zname
                                break
                        pub = None
                        try:
                            dt = parsedate_to_datetime(item.findtext("pubDate") or "")
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            pub = dt.isoformat()
                        except (TypeError, ValueError):
                            pass
                        events.append(Event(
                            source=self.source,
                            source_id=f"es_news:{feed_name}:{guid[:70]}",
                            event_type="news",
                            lat=lat,
                            lon=lon,
                            level="info",
                            title=title or "Migración España",
                            description=(description[:500] + ("…" if len(description) > 500 else "")) or "",
                            country=label,
                            iso3="ESP",
                            category="news",
                            admin_level="incident",
                            reported_at=pub,
                            raw_json={"url": link, "source": feed_name},
                        ))
                except Exception as e:
                    logger.error("[es_news] %s error: %s", feed_name, e)
        logger.info("[es_news] %d noticias de migración en España", len(events))
        return events
