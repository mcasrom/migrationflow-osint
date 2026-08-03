"""Colector de noticias humanitarias — ReliefWeb RSS (UNHCR, IOM, OCHA, ECHO...).

Feed público sin appname. Se filtran por palabras clave de migración/refugio y
se geolocalizan por país (categorías del feed o etiqueta Country/Countries).
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from src.config import (RELIEFWEB_RSS, NEWS_KEYWORDS, NEWS_MAX_ITEMS,
                        HTTP_TIMEOUT, USER_AGENT)
from src.logging import get_logger
from src.models import Event
from src.collectors.base import BaseCollector
from src.collectors.countries import match_country_by_name
from src.geocode import refine

logger = get_logger("src.collectors.news")

_COUNTRY_RE = re.compile(r"Country(?:s)?:\s*([^<]+)", re.IGNORECASE)


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


class NewsCollector(BaseCollector):
    name = "news"
    source = "news"

    async def collect(self) -> list[Event]:
        events: list[Event] = []
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            resp = await client.get(RELIEFWEB_RSS, follow_redirects=True)
            resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall("channel/item")[:NEWS_MAX_ITEMS]

        for item in items:
            title = _clean_html(item.findtext("title"))
            description = _clean_html(item.findtext("description"))
            link = (item.findtext("link") or "").strip()
            guid = item.findtext("guid") or link
            haystack = f"{title} {description}".lower()
            if not any(kw in haystack for kw in NEWS_KEYWORDS):
                continue

            geo = self._geo_from_item(item, description)
            if not geo:
                continue

            fine = refine(geo.get("iso3", ""), geo["lat"], geo["lon"], title, description)
            label = fine["name"] or geo["name"]
            if fine["name"]:
                logger.info("[news] geocoding fino: %s (%s) → %s,%s",
                            fine["name"], geo.get("iso3"), fine["lat"], fine["lon"])

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
                source_id=f"news:{guid[:80]}",
                event_type="news",
                lat=fine["lat"],
                lon=fine["lon"],
                level="info",
                title=title or "Noticia humanitaria",
                description=(description[:500] + ("…" if len(description) > 500 else "")) or "",
                country=label,
                iso3=geo.get("iso3", ""),
                category="news",
                admin_level="incident",
                reported_at=pub,
                raw_json={"url": link, "source": self._item_source(item)},
            ))
        logger.info("[news] %d noticias relevantes geolocalizadas", len(events))
        return events

    def _geo_from_item(self, item, description: str):
        """Primero categorías del feed que sean países, luego etiqueta Country(s)."""
        for cat in item.findall("category"):
            g = match_country_by_name(cat.text)
            if g:
                return g
        m = _COUNTRY_RE.search(description)
        if m:
            first = m.group(1).split(",")[0].strip()
            return match_country_by_name(first)
        return None

    def _item_source(self, item) -> str:
        return "ReliefWeb"
