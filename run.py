"""Punto de entrada del pipeline de colectores.

Uso:
    python run.py                        # ejecuta todos los colectores
    python run.py --collectors unhcr,idmc
    python run.py --init-db --collectors iom_dtm
"""
import argparse
import asyncio
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from src.logging import get_logger  # noqa: E402
from src.db import init_db, expire_events, fetch_summary  # noqa: E402

logger = get_logger("mf.run")

COLLECTORS = {
    "unhcr": ("src.collectors.unhcr", "UNHCRCollector"),
    "idmc": ("src.collectors.idmc", "IDMCCollector"),
    "iom_dtm": ("src.collectors.iom_dtm", "IOMDTMCollector"),
    "missing_migrants": ("src.collectors.missing_migrants", "MissingMigrantsCollector"),
    "frontex": ("src.collectors.frontex", "FrontexCollector"),
    "caminando_fronteras": ("src.collectors.caminando_fronteras", "CaminandoFronterasCollector"),
    "news": ("src.collectors.news", "NewsCollector"),
}


def build_collectors(names: list[str]):
    out = []
    for n in names:
        mod_path, cls = COLLECTORS[n]
        mod = __import__(mod_path, fromlist=[cls])
        out.append(getattr(mod, cls)())
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description="MigrationFlow OSINT pipeline")
    parser.add_argument("--collectors", default=",".join(COLLECTORS),
                        help="Colectores a ejecutar, separados por coma")
    parser.add_argument("--init-db", action="store_true",
                        help="Inicializa el esquema de la BD antes de ejecutar")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    names = [n.strip() for n in args.collectors.split(",") if n.strip()]
    unknown = [n for n in names if n not in COLLECTORS]
    if unknown:
        logger.error("Colectores desconocidos: %s", unknown)
        raise SystemExit(1)

    logger.info("=== Pipeline MigrationFlow OSINT (%s) — %s ===",
                ", ".join(names), datetime.now(timezone.utc).isoformat())

    init_db()
    expired = expire_events()
    if expired:
        logger.info("[run] eventos expirados: %d", expired)

    for col in build_collectors(names):
        await col.run()

    summary = fetch_summary()
    logger.info("[run] resumen: %s", summary)


if __name__ == "__main__":
    asyncio.run(main())
