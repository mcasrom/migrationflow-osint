from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

EVENT_STATUS_ACTIVE = "active"
EVENT_STATUS_EXPIRED = "expired"

LEVELS = {"info": "info", "warning": "warning", "alert": "alert", "critical": "critical"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_int(n) -> str:
    """Formatea un entero con separadores de miles (es-ES)."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


@dataclass
class Event:
    source: str
    source_id: str
    event_type: str
    lat: float
    lon: float
    level: str = "info"
    title: str = ""
    description: str = ""
    country: str = ""
    iso3: str = ""
    category: str = "stock"
    admin_level: str = "admin0"
    value: Optional[float] = None
    value_type: str = ""
    status: str = EVENT_STATUS_ACTIVE
    raw_json: Optional[dict] = None
    reported_at: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    id: Optional[int] = None

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if v is not None:
                d[k] = v
        return d
