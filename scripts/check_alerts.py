"""Detecta picos de incidentes por zona y bulos en noticias, y envía push.

Cron sugerido: 15 */6 * * * (cada 6 horas).
Requisitos: pywebpush + VAPID en .env (ver src/push.py).
"""
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2.extras

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db, push
from src.bulos import TOPICS, BULOS, _norm, _tokens
from src.logging import get_logger

logger = get_logger("src.alerts")

REGIONS = {
    "global": None,
    "esp": {"ESP"},
    "mar": {"MAR"},
    "med": {"ESP", "MAR", "ITA", "GRC", "TUR", "LBY", "TUN", "EGY", "ALB", "MNE", "BIH", "HRV"},
}

SPIKE_MIN_INCIDENTS = 2
SPIKE_RATIO = 1.5


def _ensure_log_table():
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_log (
                alert_key TEXT PRIMARY KEY,
                last_sent TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.commit()
    finally:
        db.release_conn(conn)


def _already_sent(key: str) -> bool:
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM alert_log WHERE alert_key=%s", (key,))
        return cur.fetchone() is not None
    finally:
        db.release_conn(conn)


def _mark_sent(key: str):
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO alert_log (alert_key) VALUES (%s) ON CONFLICT DO NOTHING", (key,))
        conn.commit()
    finally:
        db.release_conn(conn)


def check_spikes():
    today = date.today()
    for region, iso3s in REGIONS.items():
        cur7 = db.incident_stats_iso3(iso3s, 7)
        prev7 = db.incident_stats_iso3(iso3s, 14)
        cur_count = cur7["count"] if cur7 else 0
        prev_count = (prev7["count"] if prev7 else 0) - cur_count
        if cur_count >= SPIKE_MIN_INCIDENTS and prev_count >= 0 and prev7:
            if cur_count >= prev_count * SPIKE_RATIO and cur_count > prev_count:
                key = f"spike:{region}:{today.isoformat()}"
                if _already_sent(key):
                    continue
                es = {
                    "title": "Pico de incidentes en el Mediterráneo",
                    "body": f"{cur_count} incidentes con víctimas registrados en la última semana en tu zona ({region}). Ver datos oficiales.",
                }
                en = {
                    "title": "Incident spike in the Mediterranean",
                    "body": f"{cur_count} incidents with victims recorded in the last week in your area ({region}). See official data.",
                }
                push.send(es["title"], es["body"], "/", region=region, lang="es")
                push.send(en["title"], en["body"], "/", region=region, lang="en")
                _mark_sent(key)
                logger.info("[alerts] spike enviado region=%s cur=%d prev=%d", region, cur_count, prev_count)


def check_topics_in_news():
    """Busca noticias recientes que mencionen tópicos de contexto/bulos y avisa."""
    tokens_of_interest = set()
    for tp in TOPICS:
        tokens_of_interest.update(_tokens(" ".join(tp["keywords"])))
    for b in BULOS:
        tokens_of_interest.update(_tokens(" ".join(b["keywords"])))
    if not tokens_of_interest:
        return
    conn = db.get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, title, country, iso3 FROM events "
            "WHERE status='active' AND event_type='news' "
            "AND reported_at >= now() - interval '7 days' "
            "ORDER BY reported_at DESC LIMIT 50")
        rows = cur.fetchall()
    finally:
        db.release_conn(conn)
    for ev in rows:
        toks = _tokens(ev["title"] or "")
        hit = toks and any(t in tokens_of_interest for t in toks)
        if not hit:
            continue
        key = f"topic:{ev['id']}"
        if _already_sent(key):
            continue
        push.send(
            title="¿Noticia sobre migración? Verifica antes de compartir",
            body=f"Ha aparecido una noticia que toca un tema con bulos recurrentes. Compruébala con datos.",
            url="/",
            region="global",
        )
        _mark_sent(key)


def main():
    _ensure_log_table()
    check_spikes()
    check_topics_in_news()
    logger.info("[alerts] revisión completada %s", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main()
