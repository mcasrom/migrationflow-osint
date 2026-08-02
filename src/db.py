import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from src.logging import get_logger
from src.models import Event, EVENT_STATUS_ACTIVE, EVENT_STATUS_EXPIRED
from src.config import POOL_MINCONN, POOL_MAXCONN, SOURCE_TTL_DAYS

logger = get_logger("src.db")

DB_CONFIG = {
    "dbname": os.environ.get("DB_NAME", "migrationflow"),
    "user": os.environ.get("DB_USER", "mf"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
}

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=POOL_MINCONN, maxconn=POOL_MAXCONN, **DB_CONFIG
        )
    return _pool


def get_conn():
    conn = get_pool().getconn()
    conn.autocommit = False
    return conn


def release_conn(conn):
    try:
        conn.rollback()
    except Exception:
        pass
    get_pool().putconn(conn)


def init_db():
    """Crea las tablas e índices (idempotente)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'stock',
                level TEXT NOT NULL DEFAULT 'info',
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                iso3 TEXT NOT NULL DEFAULT '',
                admin_level TEXT NOT NULL DEFAULT 'admin0',
                value DOUBLE PRECISION,
                value_type TEXT NOT NULL DEFAULT '',
                lat DOUBLE PRECISION NOT NULL,
                lon DOUBLE PRECISION NOT NULL,
                geom GEOGRAPHY(POINT, 4326),
                reported_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                status TEXT NOT NULL DEFAULT 'active',
                raw_json JSONB,
                CONSTRAINT events_source_id_key UNIQUE (source, source_id)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_geom ON events USING GIST (geom)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_iso3 ON events (iso3)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events (status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_expires ON events (expires_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_updated ON events (updated_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_level ON events (level)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS collector_runs (
                id BIGSERIAL PRIMARY KEY,
                collector TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                finished_at TIMESTAMPTZ,
                success BOOLEAN,
                events_created INT DEFAULT 0,
                events_updated INT DEFAULT 0,
                error TEXT DEFAULT '',
                meta JSONB
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_collector ON collector_runs (collector, started_at DESC)")
        conn.commit()
        logger.info("[init_db] esquema listo")
    except Exception as e:
        conn.rollback()
        logger.error("[init_db] error: %s", e)
        raise
    finally:
        release_conn(conn)


def _ttl_for(source: str) -> timedelta:
    return timedelta(days=SOURCE_TTL_DAYS.get(source, 90))


def _compute_expiry(ev: Event) -> Optional[str]:
    """Expiración por defecto = ahora + TTL de la fuente.

    Si el colector fija `expires_at` explícitamente (p. ej. incidentes anclados
    a su fecha), se respeta. Para stock, cada ejecución renueva el TTL, de modo
    que un evento desaparece TTL días después de que la fuente deje de devolverlo.
    """
    if ev.expires_at:
        return ev.expires_at
    return (datetime.now(timezone.utc) + _ttl_for(ev.source)).isoformat()


def save_events_batch(events: list[Event]) -> tuple[int, int]:
    """Upsert por (source, source_id). Devuelve (creados, actualizados)."""
    if not events:
        return 0, 0
    conn = get_conn()
    created = updated = 0
    try:
        cur = conn.cursor()
        for ev in events:
            lat = float(ev.lat)
            lon = float(ev.lon)
            expires = _compute_expiry(ev)
            reported = ev.reported_at
            if reported:
                reported = reported.replace("Z", "+00:00")
            raw = json.dumps(ev.raw_json) if ev.raw_json is not None else None
            cur.execute(
                """
                INSERT INTO events
                    (source, source_id, event_type, category, level, title, description,
                     country, iso3, admin_level, value, value_type, lat, lon, geom,
                     reported_at, expires_at, updated_at, status, raw_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s,%s, now(), %s, %s)
                ON CONFLICT (source, source_id) DO UPDATE SET
                    event_type = EXCLUDED.event_type,
                    category = EXCLUDED.category,
                    level = EXCLUDED.level,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    country = EXCLUDED.country,
                    iso3 = EXCLUDED.iso3,
                    admin_level = EXCLUDED.admin_level,
                    value = EXCLUDED.value,
                    value_type = EXCLUDED.value_type,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon,
                    geom = EXCLUDED.geom,
                    reported_at = EXCLUDED.reported_at,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = now(),
                    status = EXCLUDED.status,
                    raw_json = EXCLUDED.raw_json
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    ev.source, ev.source_id, ev.event_type, ev.category, ev.level,
                    ev.title, ev.description, ev.country, ev.iso3, ev.admin_level,
                    ev.value, ev.value_type, lat, lon, lon, lat,
                    reported, expires, ev.status, raw,
                ),
            )
            row = cur.fetchone()
            if row and row[0]:
                created += 1
            else:
                updated += 1
        conn.commit()
        logger.info("[db] %d creados, %d actualizados (%s)", created, updated, events[0].source)
        return created, updated
    except Exception as e:
        conn.rollback()
        logger.error("[db] save_events_batch error: %s", e)
        raise
    finally:
        release_conn(conn)


def expire_events() -> int:
    """Marca como expirados los eventos activos cuya fecha de expiración ha pasado."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE events SET status=%s, updated_at=now() "
            "WHERE status=%s AND expires_at < now()",
            (EVENT_STATUS_EXPIRED, EVENT_STATUS_ACTIVE),
        )
        n = cur.rowcount
        conn.commit()
        if n:
            logger.info("[db] %d eventos expirados", n)
        return n
    except Exception as e:
        conn.rollback()
        logger.error("[db] expire_events error: %s", e)
        return 0
    finally:
        release_conn(conn)


def record_run_start(collector: str) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO collector_runs (collector) VALUES (%s) RETURNING id", (collector,))
        rid = cur.fetchone()[0]
        conn.commit()
        return rid
    finally:
        release_conn(conn)


def record_run_end(run_id: int, success: bool, created: int, updated: int, error: str = "", meta: Optional[dict] = None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE collector_runs SET finished_at=now(), success=%s, events_created=%s, "
            "events_updated=%s, error=%s, meta=%s WHERE id=%s",
            (success, created, updated, error, json.dumps(meta) if meta else None, run_id),
        )
        conn.commit()
    finally:
        release_conn(conn)


def fetch_events(types: Optional[list] = None, min_level: Optional[str] = None,
                 max_age_days: Optional[int] = None, bbox: Optional[tuple] = None,
                 year: Optional[int] = None, limit: int = 1000) -> list[dict]:
    """Consulta eventos activos con filtros opcionales."""
    where = ["status = 'active'"]
    params: list = []
    if types:
        where.append("event_type = ANY(%s)")
        params.append(types)
    if min_level and min_level in ("info", "warning", "alert", "critical"):
        rank = {"info": 0, "warning": 1, "alert": 2, "critical": 3}[min_level]
        where.append("CASE level WHEN 'info' THEN 0 WHEN 'warning' THEN 1 "
                     "WHEN 'alert' THEN 2 ELSE 3 END >= %s")
        params.append(rank)
    if max_age_days:
        where.append("reported_at >= now() - make_interval(days => %s)")
        params.append(int(max_age_days))
    if year:
        where.append("date_part('year', reported_at) = %s")
        params.append(int(year))
    if bbox:
        west, south, east, north = bbox
        where.append("geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)::geography")
        params.extend([west, south, east, north])
    sql = f"""
        SELECT id, source, source_id, event_type, category, level, title, description,
               country, iso3, admin_level, value, value_type, lat, lon,
               reported_at, expires_at, updated_at, raw_json
        FROM events
        WHERE {' AND '.join(where)}
        ORDER BY updated_at DESC
        LIMIT %s
    """
    params.append(int(limit))
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = list(cur.fetchall())
        for r in rows:
            r["reported_at"] = r["reported_at"].isoformat() if r["reported_at"] else None
            r["expires_at"] = r["expires_at"].isoformat() if r["expires_at"] else None
            r["updated_at"] = r["updated_at"].isoformat() if r["updated_at"] else None
        return rows
    finally:
        release_conn(conn)


def fetch_country_summary(iso3: str, days: int = 365) -> Optional[dict]:
    """Resumen de un país: stocks (último dato disponible) + actividad en los
    últimos `days` días + delta vs. el período previo equivalente."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            "SELECT country FROM events WHERE iso3=%s AND status='active' "
            "AND country<>'' ORDER BY updated_at DESC LIMIT 1", (iso3,))
        row = cur.fetchone()
        if not row:
            return None
        name = row["country"]

        cur.execute(
            "SELECT DISTINCT ON (event_type) event_type, value, reported_at "
            "FROM events WHERE iso3=%s AND status='active' "
            "AND event_type IN ('refugees','asylum','idp','displacement','dtm_idp') "
            "ORDER BY event_type, reported_at DESC", (iso3,))
        stocks = [
            {"type": r["event_type"], "value": r["value"],
             "reported_at": r["reported_at"].isoformat() if r["reported_at"] else None}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT event_type, count(*) AS n, round(sum(value)::numeric) AS total, "
            "min(reported_at)::date AS from_d, max(reported_at)::date AS to_d "
            "FROM events WHERE iso3=%s AND status='active' "
            "AND reported_at >= now() - make_interval(days => %s) "
            "GROUP BY event_type", (iso3, days))
        activity = {}
        for r in cur.fetchall():
            activity[r["event_type"]] = {
                "count": r["n"],
                "sum": float(r["total"]) if r["total"] is not None else None,
                "from": str(r["from_d"]) if r["from_d"] else None,
                "to": str(r["to_d"]) if r["to_d"] else None,
            }

        cur.execute(
            "SELECT event_type, count(*) AS n, round(sum(value)::numeric) AS total "
            "FROM events WHERE iso3=%s AND status='active' "
            "AND reported_at >= now() - make_interval(days => %s) "
            "AND reported_at < now() - make_interval(days => %s) "
            "GROUP BY event_type", (iso3, days * 2, days))
        delta = {}
        for r in cur.fetchall():
            delta[r["event_type"]] = {
                "count": r["n"],
                "sum": float(r["total"]) if r["total"] is not None else None,
            }

        cur.execute(
            "SELECT round(sum(value)::numeric) FROM events "
            "WHERE iso3=%s AND status='active' AND value IS NOT NULL", (iso3,))
        affected = cur.fetchone()["round"]

        return {"iso3": iso3, "name": name, "days": days,
                "affected": float(affected) if affected is not None else None,
                "stocks": stocks, "activity": activity, "delta": delta}
    finally:
        release_conn(conn)


def fetch_summary() -> dict:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM events WHERE status='active'")
        total = cur.fetchone()[0]
        cur.execute("SELECT event_type, count(*) FROM events WHERE status='active' GROUP BY 1")
        by_type = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT level, count(*) FROM events WHERE status='active' GROUP BY 1")
        by_level = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT count(*) FROM events WHERE status='active' AND value IS NOT NULL")
        with_value = cur.fetchone()[0]
        cur.execute("SELECT sum(value) FROM events WHERE status='active' AND value IS NOT NULL")
        sum_value = cur.fetchone()[0]
        return {
            "total_active": total,
            "by_type": by_type,
            "by_level": by_level,
            "with_value": with_value,
            "sum_value": sum_value,
        }
    finally:
        release_conn(conn)


def fetch_status() -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT DISTINCT ON (collector) collector, success, started_at, finished_at, "
            "events_created, events_updated, error "
            "FROM collector_runs ORDER BY collector, started_at DESC"
        )
        rows = list(cur.fetchall())
        for r in rows:
            r["started_at"] = r["started_at"].isoformat() if r["started_at"] else None
            r["finished_at"] = r["finished_at"].isoformat() if r["finished_at"] else None
        return rows
    finally:
        release_conn(conn)
