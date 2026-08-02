"""Envío de notificaciones Web Push (VAPID).

Requiere: pip install pywebpush
Configuración en .env:
    VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT
"""

import json
import os

from src import db
from src.logging import get_logger

logger = get_logger("src.push")

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:migrationflow@viajeinteligencia.com")


def public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "")


def _send_one(sub: dict, payload: dict) -> bool:
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.error("[push] pywebpush no instalado")
        return False
    subscription = {
        "endpoint": sub["endpoint"],
        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
    }
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=10,
        )
        return True
    except WebPushException as e:
        if e.response and e.response.status_code in (404, 410):
            logger.info("[push] suscripción inválida, eliminada: %s", e.response.status_code)
            db.push_subscription_remove(sub["endpoint"])
        elif e.response and e.response.status_code in (401, 403):
            logger.warning("[push] 401/403, desactivada: %s", e.response.status_code)
            db.push_subscription_delete(sub["endpoint"])
        else:
            logger.warning("[push] error (%s): %s", getattr(e.response, "status_code", None), e)
        return False


def send(title: str, body: str, url: str, region: str = "global", lang: str = "es",
         icon: str = "/icon-192.png", badge: str = "/icon-192.png") -> tuple[int, int]:
    """Envía a todas las suscripciones de una región. Devuelve (ok, fail)."""
    subs = db.push_subscriptions_for(region)
    if not subs:
        logger.info("[push] sin suscripciones para región %s", region)
        return 0, 0
    payload = {
        "title": title if lang == "es" else title,
        "body": body,
        "url": url,
        "icon": icon,
        "badge": badge,
        "tag": "migrationflow",
    }
    ok = fail = 0
    for s in subs:
        s_lang = s.get("lang", lang)
        p = dict(payload)
        if s_lang != "es":
            # El mensaje ya se pasa en el idioma correcto desde el llamador
            p["body"] = body
        if _send_one(s, p):
            ok += 1
        else:
            fail += 1
    logger.info("[push] %d enviadas, %d fallidas (región %s)", ok, fail, region)
    return ok, fail
