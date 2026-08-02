"""API FastAPI de MigrationFlow OSINT."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.logging import get_logger
from src.db import init_db, fetch_events, fetch_summary, fetch_status
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
                        max_age_days=max_age_days, bbox=bbox_tuple, limit=limit)
    return {"total": len(rows), "events": rows}


@app.get("/api/summary")
def api_summary():
    return fetch_summary()


@app.get("/api/status")
def api_status():
    return {"collectors": fetch_status(), "event_types": EVENT_TYPES}


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=str(FRONTEND)), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
