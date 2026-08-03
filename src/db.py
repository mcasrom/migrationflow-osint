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
            CREATE TABLE IF NOT EXISTS arrivals_series (
                country_iso3 TEXT NOT NULL,
                month DATE NOT NULL,
                value DOUBLE PRECISION NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (country_iso3, month)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_arrivals_series_month ON arrivals_series (month)")
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id BIGSERIAL PRIMARY KEY,
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT 'global',
                lang TEXT NOT NULL DEFAULT 'es',
                enabled BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_push_region ON push_subscriptions (region, enabled)")
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


def expire_source_type(source: str, event_type: str) -> int:
    """Expira todos los eventos activos de un (source, event_type).

    Se usa cuando una fuente nueva (p. ej. un informe más reciente) sustituye
    por completo a la anterior para evitar duplicar datos en el mapa.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE events SET status=%s, updated_at=now() "
            "WHERE source=%s AND event_type=%s AND status=%s",
            (EVENT_STATUS_EXPIRED, source, event_type, EVENT_STATUS_ACTIVE),
        )
        n = cur.rowcount
        conn.commit()
        if n:
            logger.info("[db] %d eventos expirados (%s/%s)", n, source, event_type)
        return n
    except Exception as e:
        conn.rollback()
        logger.error("[db] expire_source_type error: %s", e)
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
            "AND event_type IN ('refugees','asylum','refugees_origin','idp','displacement','dtm_idp') "
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
            "AND event_type NOT IN ('arrivals','arrivals_route') "
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
            "AND event_type NOT IN ('arrivals','arrivals_route') "
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
            "SELECT round(sum(value)::numeric) FROM ("
            "SELECT DISTINCT ON (event_type) value FROM events "
            "WHERE iso3=%s AND status='active' "
            "AND event_type IN ('refugees','asylum','refugees_origin','idp','displacement','dtm_idp') "
            "ORDER BY event_type, reported_at DESC) t", (iso3,))
        affected = cur.fetchone()["round"]

        cur.execute(
            "SELECT value, to_char(reported_at, 'YYYY') AS year FROM events "
            "WHERE iso3=%s AND status='active' AND event_type='arrivals' "
            "AND value IS NOT NULL ORDER BY reported_at DESC LIMIT 1", (iso3,))
        ar = cur.fetchone()
        arrivals = {"value": float(ar["value"]), "year": ar["year"]} if ar else None

        return {"iso3": iso3, "name": name, "days": days,
                "affected": float(affected) if affected is not None else None,
                "stocks": stocks, "activity": activity, "delta": delta,
                "arrivals": arrivals}
    finally:
        release_conn(conn)


def fetch_summary(year: Optional[int] = None) -> dict:
    conn = get_conn()
    yw = ""
    params = []
    if year:
        yw = "AND date_part('year', reported_at) = %s"
        params.append(int(year))
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT count(*) FROM events WHERE status='active' {yw}", params)
        total = cur.fetchone()[0]
        cur.execute(f"SELECT event_type, count(*) FROM events WHERE status='active' {yw} GROUP BY 1", params)
        by_type = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute(f"SELECT level, count(*) FROM events WHERE status='active' {yw} GROUP BY 1", params)
        by_level = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute(f"SELECT count(*) FROM events WHERE status='active' AND value IS NOT NULL {yw}", params)
        with_value = cur.fetchone()[0]
        cur.execute(
            f"SELECT round(sum(value)::numeric) FROM ("
            "SELECT DISTINCT ON (iso3, event_type) value FROM events "
            f"WHERE status='active' AND value IS NOT NULL {yw} "
            "AND event_type IN ('refugees','asylum','refugees_origin','idp','displacement','dtm_idp') "
            "ORDER BY iso3, event_type, reported_at DESC) t", params)
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


def save_arrivals_series(rows: list[tuple]) -> int:
    """Upsert de la serie mensual de entradas Frontex.

    Cada fila es (country_iso3, month 'YYYY-MM-DD', value). No crea eventos:
    alimenta la tendencia y los gráficos sin saturar el mapa.
    """
    if not rows:
        return 0
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executemany(
            """INSERT INTO arrivals_series (country_iso3, month, value, updated_at)
               VALUES (%s, %s, %s, now())
               ON CONFLICT (country_iso3, month) DO UPDATE SET
                 value = EXCLUDED.value, updated_at = now()""",
            rows)
        conn.commit()
        logger.info("[db] %d puntos de serie mensual (arrivals_series)", len(rows))
        return len(rows)
    except Exception as e:
        conn.rollback()
        logger.error("[db] save_arrivals_series error: %s", e)
        raise
    finally:
        release_conn(conn)


def fetch_arrivals_series(country: Optional[str] = None, months: int = 24) -> dict:
    """Serie mensual de entradas Frontex; global (suma de países) o por país."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if country:
            cur.execute(
                "SELECT to_char(month, 'YYYY-MM') AS month, value "
                "FROM arrivals_series WHERE country_iso3=%s "
                "AND month >= date_trunc('month', now()) - make_interval(months => %s) "
                "ORDER BY month", (country, int(months)))
            rows = list(cur.fetchall())
            return {"country": country, "asof": _series_asof(cur),
                    "points": [{"month": r["month"], "value": float(r["value"])}
                               for r in rows]}
        cur.execute(
            "SELECT to_char(month, 'YYYY-MM') AS month, round(sum(value)::numeric) AS value "
            "FROM arrivals_series "
            "WHERE month >= date_trunc('month', now()) - make_interval(months => %s) "
            "GROUP BY month ORDER BY month", (int(months),))
        rows = list(cur.fetchall())
        return {"country": None, "asof": _series_asof(cur),
                "points": [{"month": r["month"], "value": float(r["value"])}
                           for r in rows]}
    finally:
        release_conn(conn)


def _series_asof(cur) -> Optional[str]:
    """Último mes completo disponible en arrivals_series (misma conexión)."""
    cur.execute("SELECT max(month) FROM arrivals_series WHERE month < date_trunc('month', now())")
    r = cur.fetchone()
    return r["max"].strftime("%Y-%m") if r and r["max"] else None


def fetch_arrivals_trend() -> dict:
    """Tendencia de entradas por país de origen: acumulado del año actual vs.
    mismo periodo del año anterior (comparable), a partir de la serie mensual."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH asof AS (SELECT max(month) AS m FROM arrivals_series
                          WHERE month < date_trunc('month', now())),
            cur AS (
                SELECT country_iso3, sum(value) AS v FROM arrivals_series, asof
                WHERE month >= date_trunc('year', now()) AND month <= asof.m
                GROUP BY country_iso3
            ),
            prev AS (
                SELECT country_iso3, sum(value) AS v FROM arrivals_series, asof
                WHERE month >= date_trunc('year', now()) - make_interval(years => 1)
                  AND month <= asof.m - make_interval(years => 1)
                GROUP BY country_iso3
            )
            SELECT c.country_iso3 AS iso3, c.v AS current_value, p.v AS prev_value
            FROM cur c LEFT JOIN prev p ON p.country_iso3 = c.country_iso3
        """)
        countries = {}
        for r in cur.fetchall():
            c = float(r["current_value"])
            p = float(r["prev_value"]) if r["prev_value"] is not None else None
            pct = None if p is None or p == 0 else round((c - p) / p * 100, 1)
            countries[r["iso3"]] = {"current": c, "prev": p, "pct": pct}
        return {"asof": _series_asof(cur), "countries": countries}
    finally:
        release_conn(conn)


def fetch_monthly_incidents(months: int = 12) -> list[dict]:
    """Serie mensual de incidentes missing (count y muertes) en los últimos N meses."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT to_char(reported_at, 'YYYY-MM') AS month, count(*) AS n, "
            "coalesce(round(sum(value)::numeric), 0) AS deaths "
            "FROM events WHERE status='active' AND event_type='missing' "
            "AND reported_at >= date_trunc('month', now()) - make_interval(months => %s) "
            "GROUP BY 1 ORDER BY 1", (int(months),))
        return [{"month": r["month"], "count": r["n"], "deaths": float(r["deaths"])}
                for r in cur.fetchall()]
    finally:
        release_conn(conn)


def fetch_top_countries(limit: int = 10) -> list[dict]:
    """Top países por personas afectadas (último snapshot por tipo de stock)."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT iso3, country, round(sum(value)::numeric) AS value FROM ("
            "SELECT DISTINCT ON (iso3, event_type) iso3, country, value "
            "FROM events WHERE status='active' AND value IS NOT NULL "
            "AND event_type IN "
            "('refugees','asylum','refugees_origin','idp','displacement','dtm_idp') "
            "ORDER BY iso3, event_type, reported_at DESC) t "
            "GROUP BY iso3, country ORDER BY value DESC LIMIT %s", (int(limit),))
        return [{"iso3": r["iso3"], "country": r["country"], "value": float(r["value"])}
                for r in cur.fetchall()]
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


# ── Verificador de bulos / contexto ─────────────────────────────────

def search_events(text: str, limit: int = 20) -> list[dict]:
    """Busca eventos activos cuyo título/descripción contenga los tokens de `text`."""
    import re as _re
    tokens = _re.findall(r"[a-zA-Z0-9À-ÿ]{3,}", text or "")
    if not tokens:
        return []
    where, params = [], []
    for t in tokens:
        like = f"%{t}%"
        where.append("(title ILIKE %s OR description ILIKE %s)")
        params.extend([like, like])
    sql = f"""
        SELECT id, event_type, level, title, description, country, iso3,
               value, lat, lon, reported_at, source
        FROM events WHERE status='active' AND ({' OR '.join(where)})
        ORDER BY reported_at DESC NULLS LAST LIMIT %s
    """
    params.append(int(limit))
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = list(cur.fetchall())
        for r in rows:
            r["reported_at"] = r["reported_at"].isoformat() if r["reported_at"] else None
        return rows
    finally:
        release_conn(conn)


def last_stock(event_type: str, iso3: str) -> Optional[tuple]:
    """Último stock (value, fecha año) para un tipo y país."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT value, to_char(reported_at, 'YYYY') FROM events "
            "WHERE iso3=%s AND status='active' AND event_type=%s AND value IS NOT NULL "
            "ORDER BY reported_at DESC LIMIT 1", (iso3, event_type))
        r = cur.fetchone()
        return (float(r[0]), r[1]) if r else None
    finally:
        release_conn(conn)


def global_stock(event_type: str) -> Optional[float]:
    """Último valor agregado (por país, último dato) para un tipo."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT round(sum(value)::numeric) FROM ("
            "SELECT DISTINCT ON (iso3) value FROM events "
            "WHERE status='active' AND event_type=%s AND value IS NOT NULL "
            "ORDER BY iso3, reported_at DESC) t", (event_type,))
        r = cur.fetchone()
        return float(r[0]) if r and r[0] is not None else None
    finally:
        release_conn(conn)


def route_arrivals_latest(route_key: str) -> Optional[dict]:
    """Último total mensual de entradas (Frontex) para una ruta."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT value, reported_at, country FROM events "
            "WHERE iso3=%s AND status='active' AND event_type='arrivals_route' "
            "AND value IS NOT NULL ORDER BY reported_at DESC LIMIT 1", (route_key,))
        r = cur.fetchone()
        if not r:
            return None
        return {"value": float(r["value"]),
                "reported_at": r["reported_at"].isoformat(),
                "name": r["country"]}
    finally:
        release_conn(conn)


def cf_report() -> Optional[dict]:
    """Último informe de Caminando Fronteras (víctimas por ruta) + total."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT iso3, value, country, reported_at, raw_json FROM events "
            "WHERE source='caminando_fronteras' AND event_type='cf_victims' "
            "AND status='active' ORDER BY reported_at DESC, iso3")
        rows = list(cur.fetchall())
        if not rows:
            return None
        latest = [r for r in rows if r["reported_at"] == rows[0]["reported_at"]]
        raw = rows[0]["raw_json"] or {}
        return {
            "reported_at": rows[0]["reported_at"].isoformat(),
            "period": raw.get("period"),
            "total": float(sum(float(r["value"]) for r in latest)),
            "url": raw.get("url"),
            "routes": [{"key": r["iso3"], "name": r["country"],
                        "value": float(r["value"])} for r in latest],
        }
    finally:
        release_conn(conn)


def incident_stats_iso3(iso3s: Optional[set], days: int) -> Optional[dict]:
    """Estadísticas de incidentes missing (count, muertes) en `days` días."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        params: list = []
        where = "status='active' AND event_type='missing' AND reported_at >= now() - make_interval(days => %s)"
        params.append(int(days))
        if iso3s:
            where += " AND iso3 = ANY(%s)"
            params.append(sorted(iso3s))
        cur.execute(
            f"SELECT count(*), coalesce(sum(value),0) FROM events WHERE {where}", params)
        r = cur.fetchone()
        if not r or not r[0]:
            return None
        return {"count": r[0], "deaths": float(r[1])}
    finally:
        release_conn(conn)


def incident_stats_bbox(bbox: tuple, days: int) -> Optional[dict]:
    """Estadísticas de incidentes missing dentro de una caja geográfica."""
    west, south, east, north = bbox
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*), coalesce(sum(value),0) FROM events "
            "WHERE status='active' AND event_type='missing' "
            "AND reported_at >= now() - make_interval(days => %s) "
            "AND geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)::geography",
            (int(days), west, south, east, north))
        r = cur.fetchone()
        if not r or not r[0]:
            return None
        return {"count": r[0], "deaths": float(r[1])}
    finally:
        release_conn(conn)


STOCK_LABELS = {
    "refugees": {"es": "Refugiados (acogida)", "en": "Refugees hosted"},
    "asylum": {"es": "Solicitantes de asilo (stock)", "en": "Asylum-seekers (pending)"},
    "idp": {"es": "Desplazados internos", "en": "Internally displaced"},
    "displacement": {"es": "Desplazamiento", "en": "Displacement"},
    "dtm_idp": {"es": "IDP (DTM)", "en": "IDP (DTM)"},
    "refugees_origin": {"es": "Origen de refugiados", "en": "Refugee origin"},
}


def stock_label(event_type: str, lang: str = "es") -> str:
    m = STOCK_LABELS.get(event_type)
    return m[lang] if m else event_type


# ── Push notifications ───────────────────────────────────────────────

def push_subscription_upsert(endpoint: str, p256dh: str, auth: str, region: str, lang: str = "es"):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO push_subscriptions (endpoint, p256dh, auth, region, lang, enabled)
               VALUES (%s,%s,%s,%s,%s,true)
               ON CONFLICT (endpoint) DO UPDATE SET
                 p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth, region=EXCLUDED.region,
                 lang=EXCLUDED.lang, enabled=true, updated_at=now()""",
            (endpoint, p256dh, auth, region, lang))
        conn.commit()
    finally:
        release_conn(conn)


def push_subscription_delete(endpoint: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE push_subscriptions SET enabled=false, updated_at=now() WHERE endpoint=%s", (endpoint,))
        conn.commit()
    finally:
        release_conn(conn)


def push_subscriptions_for(region: str = "global") -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if region == "global":
            cur.execute("SELECT endpoint, p256dh, auth, lang FROM push_subscriptions WHERE enabled")
        else:
            cur.execute("SELECT endpoint, p256dh, auth, lang FROM push_subscriptions "
                        "WHERE enabled AND (region=%s OR region='global')", (region,))
        return list(cur.fetchall())
    finally:
        release_conn(conn)


def push_subscription_remove(endpoint: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM push_subscriptions WHERE endpoint=%s", (endpoint,))
        conn.commit()
    finally:
        release_conn(conn)
