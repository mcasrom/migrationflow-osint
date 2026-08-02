"""MigrationFlow OSINT configuration constants.

All tunable thresholds, URLs, timeouts and limits live here.
Import from this module instead of hard-coding values in collectors.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Database ─────────────────────────────────────────────────
POOL_MINCONN = 2
POOL_MAXCONN = 10

# ── Server ───────────────────────────────────────────────────
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8600
API_TITLE = "MigrationFlow OSINT API"
API_VERSION = "0.1"

# ── HTTP ─────────────────────────────────────────────────────
HTTP_TIMEOUT = 90
USER_AGENT = "MigrationFlow-OSINT/0.1"

# ── Sources ──────────────────────────────────────────────────
UNHCR_API = "https://api.unhcr.org/population/v1"
UNHCR_YEARS = [2024, 2023]            # latest first
UNHCR_PAGE_LIMIT = 100
UNHCR_COOLDOWN_MS = 300

HDX_BASE = "https://data.humdata.org/api/3/action"
HDX_DTM_URL = ("https://data.humdata.org/dataset/32d0365c-d513-4721-8d66-1b19b12c4b08/"
               "resource/80911e9b-7527-469a-a545-4074860e1288/"
               "download/global-iom-dtm-from-api-admin-0-to-2.csv")
HDX_MMP_URL = ("https://data.humdata.org/dataset/fc59785a-31d2-4018-aac7-6b9f619ae8ec/"
               "resource/99078436-9c4a-473b-a073-428304a9cf8a/"
               "download/iom-missing-migrants-project-data.csv")

# ── Event types (label en español para la UI) ────────────────
EVENT_TYPES = {
    "refugees": "Refugiados (acogida)",
    "asylum": "Solicitantes de asilo (acogida)",
    "refugees_origin": "Refugiados por origen",
    "idp": "Desplazados internos (IDP)",
    "displacement": "Desplazamiento por conflicto (IDMC)",
    "dtm_idp": "Stock IDP (IOM DTM)",
    "missing": "Muertos y desaparecidos en migración",
}

STOCK_TYPES = {"refugees", "asylum", "refugees_origin", "idp", "displacement", "dtm_idp"}
INCIDENT_TYPES = {"missing"}

# ── Minimum value to store (evita ruido) ─────────────────────
MIN_VALUE = {
    "refugees": 10000,
    "asylum": 5000,
    "refugees_origin": 50000,
    "idp": 50000,
    "displacement": 50000,
    "dtm_idp": 10000,
    "missing": 0,
}

# ── Severity thresholds (warning, alert, critical) ───────────
SEVERITY_THRESHOLDS = {
    "refugees": (100_000, 500_000, 1_000_000),
    "asylum": (30_000, 150_000, 500_000),
    "refugees_origin": (200_000, 1_000_000, 2_000_000),
    "idp": (200_000, 1_000_000, 2_000_000),
    "displacement": (100_000, 500_000, 2_000_000),
    "dtm_idp": (50_000, 300_000, 1_000_000),
    "missing": (1, 10, 100),
}

# ── TTL en días por fuente (eventos expiran solos) ───────────
SOURCE_TTL_DAYS = {
    "unhcr": 420,              # datos anuales: válidos hasta bien entrado el año siguiente
    "idmc": 420,
    "iom_dtm": 60,             # rondas semanales
    "missing_migrants": 365,
}

# ── Retención para incidentes ────────────────────────────────
MMP_RETENTION_MONTHS = 36      # solo incidentes de los últimos 36 meses
DTM_ADMIN_LEVELS = {"0"}       # granularidad del DTM a ingestar (0=país, 1=región, 2=municipio)


def severity_for(event_type: str, value: float) -> str:
    """Devuelve info/warning/alert/critical según el valor y el tipo."""
    if value is None:
        return "info"
    th = SEVERITY_THRESHOLDS.get(event_type)
    if not th:
        return "info"
    warn, alert, crit = th
    if value >= crit:
        return "critical"
    if value >= alert:
        return "alert"
    if value >= warn:
        return "warning"
    return "info"
