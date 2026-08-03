"""API FastAPI de MigrationFlow OSINT."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.logging import get_logger
from src import bulos
from src import db
from src import push
from src.db import init_db, fetch_events, fetch_summary, fetch_status, fetch_country_summary
from src.config import API_TITLE, API_VERSION, SERVER_HOST, SERVER_PORT, EVENT_TYPES

logger = get_logger("src.api")
FRONTEND = Path(__file__).resolve().parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("API MigrationFlow OSINT arrancada")
    yield


app = FastAPI(title=API_TITLE, version=API_VERSION, docs_url="/docs",
              openapi_url="/openapi.json", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": API_TITLE}


@app.get("/api/events")
def api_events(
    types: Optional[str] = Query(None, description="Tipos separados por coma"),
    min_level: Optional[str] = Query(None),
    max_age_days: Optional[int] = Query(None),
    bbox: Optional[str] = Query(None, description="oeste,sur,este,norte"),
    year: Optional[int] = Query(None, description="Año del dato (p. ej. 2024)"),
    limit: int = Query(1500, le=5000),
):
    type_list = [t.strip() for t in types.split(",")] if types else None
    bbox_tuple = None
    if bbox:
        parts = bbox.split(",")
        if len(parts) == 4:
            try:
                bbox_tuple = tuple(float(p) for p in parts)
            except ValueError:
                bbox_tuple = None
    rows = fetch_events(types=type_list, min_level=min_level,
                        max_age_days=max_age_days, bbox=bbox_tuple,
                        year=year, limit=limit)
    return {"total": len(rows), "events": rows}


@app.get("/api/summary")
def api_summary(year: Optional[int] = Query(None, description="Año del dato (p. ej. 2024)")):
    return fetch_summary(year)


@app.get("/api/country/{iso3}")
def api_country(iso3: str, days: int = Query(365, ge=30, le=730)):
    data = fetch_country_summary(iso3.strip().upper(), days)
    if data is None:
        raise HTTPException(status_code=404, detail="País sin datos")
    return data


@app.get("/api/status")
def api_status():
    return {"collectors": fetch_status(), "event_types": EVENT_TYPES}


@app.get("/api/arrivals/series")
def api_arrivals_series(
    country: Optional[str] = Query(None, description="ISO3 (vacío = serie global)"),
    months: int = Query(24, ge=1, le=48),
):
    return db.fetch_arrivals_series(country=country.strip().upper() if country else None,
                                    months=months)


@app.get("/api/trends")
def api_trends():
    """Tendencia de entradas Frontex por país (YTD actual vs. mismo periodo previo)."""
    return db.fetch_arrivals_trend()


@app.get("/api/charts")
def api_charts():
    """Datos del panel de gráficos: serie mensual de incidentes, entradas y top países."""
    return {
        "monthly_incidents": db.fetch_monthly_incidents(),
        "monthly_arrivals": db.fetch_arrivals_series(months=24)["points"],
        "arrivals_trend": db.fetch_arrivals_trend(),
        "top_countries": db.fetch_top_countries(),
    }


@app.post("/api/verify")
async def api_verify(request: Request):
    """Verificador de bulos: cruza un claim (texto o URL) con bulos curados y eventos reales."""
    body = await request.json()
    lang = "es" if (body.get("lang") or "es") != "en" else "en"
    q = (body.get("q") or "").strip()
    url = (body.get("url") or "").strip()
    fetched = None
    if not q and bulos.is_url(url):
        fetched = bulos.fetch_claim(url)
        if fetched:
            q = f"{fetched['title']} {fetched['description']}".strip()
    if not q:
        raise HTTPException(status_code=400, detail="Falta el parámetro q (texto o url)")
    if len(q) > 500:
        q = q[:500]
    matches = bulos.check_bulos(q)
    events = db.search_events(q, limit=8)
    return {
        "query": q,
        "lang": lang,
        "fetched": fetched,
        "matches": matches,
        "events": events,
        "links": [
            {"label": "Maldita.es · Migración", "url": f"https://maldita.es/migracion/?s={q.replace(' ', '+')}"},
            {"label": "Newtral", "url": f"https://www.newtral.es/?s={q.replace(' ', '+')}"},
            {"label": "Fact Check Explorer (Google)", "url": f"https://toolbox.google.com/factcheck/explorer/search/{q.replace(' ', '+')}"},
        ],
    }


@app.get("/api/context")
def api_context(q: str = Query("", max_length=500), lang: str = "es"):
    """Tarjeta de contexto con datos reales para un texto (título de evento)."""
    if not q.strip():
        return {"cards": []}
    cards = bulos.build_context(q, lang="es" if lang != "en" else "en")
    return {"query": q, "cards": cards}


@app.get("/api/push/vapid")
def api_push_vapid():
    key = push.public_key()
    if not key:
        raise HTTPException(status_code=503, detail="VAPID no configurado")
    return {"public_key": key}


@app.post("/api/push/register")
async def api_push_register(request: Request):
    body = await request.json()
    endpoint = (body.get("endpoint") or "").strip()
    keys = body.get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        raise HTTPException(status_code=400, detail="Suscripción incompleta")
    region = (body.get("region") or "global").strip() or "global"
    lang = "es" if (body.get("lang") or "es") != "en" else "en"
    db.push_subscription_upsert(endpoint, keys["p256dh"], keys["auth"], region, lang)
    return {"ok": True}


@app.post("/api/push/unregister")
async def api_push_unregister(request: Request):
    body = await request.json()
    endpoint = (body.get("endpoint") or "").strip()
    if endpoint:
        db.push_subscription_remove(endpoint)
    return {"ok": True}


@app.get("/api/push/test")
def api_push_test(region: str = "global", lang: str = "es"):
    """Envía una notificación de prueba (uso manual)."""
    ok, fail = push.send(
        title="MigrationFlow OSINT",
        body="Esto es una prueba de alertas. Suscripción correcta.",
        url="/",
        region=region,
        lang="es" if lang != "en" else "en",
    )
    return {"ok": ok, "fail": fail}


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=str(FRONTEND)), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
