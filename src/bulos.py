"""Bulos y tópicos sobre migración (curated).

Dos usos:
- `/api/verify`: dado un texto/claim, detecta si coincide con bulos conocidos
  y recurrentes (todos documentados y desmentidos por verificadores).
- `/api/context`: dado el título de un evento, genera tarjetas de contexto
  con datos oficiales de la propia BD (p. ej. cifras reales de Ceuta).

Los textos son revisados manualmente y apuntan a fuentes verificadoras
(Maldita Migración, Newtral) y datos oficiales (UNHCR, IOM MMP).
"""

import re
import unicodedata

from src import db


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return re.sub(r"[\u0300-\u036f]+", "", s)


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _norm(s)) if len(t) >= 3]


def _hits(tokens: list[str], keywords: list[str]) -> list[str]:
    kw = sorted({_norm(k) for k in keywords}, key=len, reverse=True)
    hits = []
    for t in tokens:
        for k in kw:
            if t.startswith(k) or k.startswith(t):
                hits.append(k)
                break
    return hits


# ── Bulos recurrentes desmentidos (curados) ──────────────────────────
BULOS = [
    {
        "id": "ayudas-400-900",
        "keywords": ["400", "900", "ayuda", "subvencion", "cobran", "ingreso", "paga", "prestacion", "renta"],
        "title": {"es": "Los inmigrantes cobran ayudas de 400-900 € por el hecho de ser inmigrantes",
                  "en": "Migrants get €400-900 in benefits just for being migrants"},
        "claim": {"es": "Se repite cada cierto tiempo. En España no existe una prestación universal por ser inmigrante.",
                  "en": "A recurring claim. Spain has no universal benefit for being a migrant."},
        "evidence": {"es": "Las ayudas que existen (p. ej. RAI en algunas CCAA) son condicionadas, temporales y van dirigidas también a ciudadanos españoles; no se otorgan automáticamente por nacionalidad.",
                     "en": "Existing schemes (e.g. RAI in some regions) are conditional, temporary and also target Spanish citizens; they are not granted automatically by nationality."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "Newtral", "url": "https://www.newtral.es/"},
        ],
    },
    {
        "id": "menas-asignacion",
        "keywords": ["menas", "menor", "menores", "acompanad", "pension", "asignacion", "20.000", "20000", "30000"],
        "title": {"es": "Los menores no acompañados (menas) reciben asignaciones de 20.000 €",
                  "en": "Unaccompanied minors ('menas') receive €20,000 allowances"},
        "claim": {"es": "Falso. No existe tal asignación económica automática para los menores tutelados.",
                  "en": "False. There is no such automatic allowance for minors in care."},
        "evidence": {"es": "Los menores tutelados están bajo protección del sistema público de protección de menores, con la misma atención que cualquier otro menor en situación de tutela; la cifra de 20.000 € es un bulo desmentido reiteradamente.",
                     "en": "Children in care fall under the public child-protection system, with the same support as any other minor in custody; the €20,000 figure is a repeatedly debunked hoax."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "Newtral", "url": "https://www.newtral.es/"},
        ],
    },
    {
        "id": "ceuta-avalancha",
        "keywords": ["ceuta", "melilla", "valla", "tarajal", "avalancha", "asalt", "entrada masiva"],
        "title": {"es": "Avanzada masiva e incontrolada en la valla de Ceuta/Melilla",
                  "en": "Mass uncontrolled border crossing in Ceuta/Melilla"},
        "claim": {"es": "Conviene contrastar con datos oficiales: los incidentes registrados y las cifras oficiales suelen ser menores que las virales.",
                  "en": "Check against official data: recorded incidents and official figures are usually lower than viral ones."},
        "evidence": {"es": "Este mapa registra los incidentes con víctimas del proyecto Missing Migrants (IOM) en la zona; los datos oficiales de entradas los publican el Ministerio del Interior y Frontex.",
                     "en": "This map records the IOM Missing Migrants incidents with victims in the area; official entry figures are published by the Interior Ministry and Frontex."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "IOM Missing Migrants Project", "url": "https://missingmigrants.iom.int/"},
        ],
    },
    {
        "id": "pateras-delincuencia",
        "keywords": ["patera", "delincuente", "delincuencia", "criminal", "inseguridad"],
        "title": {"es": "Quien llega en patera es delincuente / la llegada dispara la inseguridad",
                  "en": "Arriving by boat means being a criminal / arrivals drive up insecurity"},
        "claim": {"es": "No se puede generalizar ni inferir criminalidad de la nacionalidad o la forma de llegada.",
                  "en": "Criminality cannot be inferred from nationality or arrival method."},
        "evidence": {"es": "La gran mayoría de personas que llegan por vía irregular solicitan protección y no tienen antecedentes; el bulo mezcla categorías jurídicas y estadísticas distintas.",
                     "en": "The vast majority of people arriving irregularly seek protection and have no criminal record; the hoax conflates different legal and statistical categories."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "ACNUR · Protección internacional", "url": "https://www.acnur.org/es-es/proteccion-internacional"},
        ],
    },
    {
        "id": "ayudas-automaticas",
        "keywords": ["paro", "desempleo", "renta minima", "ingreso minimo", "cobran sin", "por ser inmigrante"],
        "title": {"es": "Los inmigrantes cobran paro o renta mínima sin haber cotizado",
                  "en": "Migrants collect unemployment or minimum income without contributing"},
        "claim": {"es": "Falso: la mayoría de prestaciones exigen cotización o requisitos que también aplican a la ciudadanía.",
                  "en": "False: most benefits require contributions or conditions that apply to citizens too."},
        "evidence": {"es": "El acceso a prestaciones contributivas y no contributivas está regulado por ley y exige cumplir requisitos (cotización, residencia, situación de necesidad); no se conceden por nacionalidad.",
                     "en": "Access to contributory and non-contributory benefits is regulated by law and requires meeting conditions (contributions, residence, need); it is not granted by nationality."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "Seguridad Social (España)", "url": "https://www.seg-social.es/"},
        ],
    },
    {
        "id": "no-pagan-impuestos",
        "keywords": ["impuesto", "impuestos", "no pagan", "ayudas y no pagan"],
        "title": {"es": "Los inmigrantes no pagan impuestos",
                  "en": "Migrants do not pay taxes"},
        "claim": {"es": "Falso: quien trabaja y consume en España paga impuestos igual que el resto.",
                  "en": "False: anyone working and consuming in Spain pays taxes like everyone else."},
        "evidence": {"es": "Las personas con permiso de trabajo cotizan a la Seguridad Social y tributan IRPF e IVA; el sistema tributario se aplica por actividad económica, no por nacionalidad.",
                     "en": "People with a work permit contribute to social security and pay income tax and VAT; the tax system applies by economic activity, not nationality."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "Newtral", "url": "https://www.newtral.es/"},
        ],
    },
]


# ── Tópicos para tarjeta de contexto (con datos de la BD) ────────────
CEUTA_BBOX = (-6.5, 35.0, -2.0, 36.3)   # Estrecho / Ceuta / Melilla
MEDITERRANEO_W = {"ESP", "MAR", "ITA", "GRC", "TUR", "LBY", "TUN", "EGY", "ALB", "MNE", "BIH", "HRV"}

TOPICS = [
    {
        "id": "ceuta",
        "keywords": ["ceuta", "melilla", "valla", "tarajal", "estrecho"],
        "label": {"es": "Ceuta y Melilla", "en": "Ceuta & Melilla"},
        "points": [
            ("incidents", "missing", "CEUTA_BBOX", 365),
            ("stocks", "asylum", "ESP", None),
            ("stocks", "refugees", "ESP", None),
        ],
    },
    {
        "id": "mediterraneo",
        "keywords": ["patera", "mediterrane", "naufragio", "rescate", "ruta"],
        "label": {"es": "Ruta del Mediterráneo", "en": "Mediterranean route"},
        "points": [
            ("region_incidents", "missing", "MEDITERRANEO_W", 365),
            ("global_missing", None, None, 365),
        ],
    },
    {
        "id": "asilo",
        "keywords": ["asilo", "solicitante", "proteccion internacional", "acnur"],
        "label": {"es": "Asilo y protección", "en": "Asylum & protection"},
        "points": [
            ("stocks", "asylum", "ESP", None),
            ("global_stock", "refugees", None, None),
        ],
    },
]


def _match_keywords(text: str) -> list[str]:
    return _tokens(text)


def check_bulos(text: str) -> list[dict]:
    """Devuelve los bulos curados cuyas keywords coinciden con `text`."""
    if not text:
        return []
    tok = _match_keywords(text)
    results = []
    for b in BULOS:
        hits = _hits(tok, b["keywords"])
        if hits:
            results.append({"id": b["id"], "title": b["title"], "claim": b["claim"],
                            "evidence": b["evidence"], "sources": b["sources"],
                            "matched": len(hits), "matched_keywords": hits[:6]})
    results.sort(key=lambda x: x["matched"], reverse=True)
    return results[:4]


def _point_label(kind: str, lang: str) -> str:
    labels = {
        "incidents": {"es": "Incidentes con víctimas (MMP) en la zona", "en": "Incidents with victims (MMP) in the area"},
        "region_incidents": {"es": "Incidentes con víctimas (MMP) en la región", "en": "Incidents with victims (MMP) in the region"},
        "global_missing": {"es": "Muertes registradas (MMP)", "en": "Recorded deaths (MMP)"},
        "stocks": {"es": None, "en": None},          # usa etiqueta del tipo
        "global_stock": {"es": "Refugiados en el mundo (UNHCR)", "en": "Refugees worldwide (UNHCR)"},
    }
    return labels[kind][lang]


def build_context(text: str, lang: str = "es", days: int = 365) -> list[dict]:
    """Genera tarjetas de contexto con datos reales para `text`."""
    if not text:
        return []
    tok = _match_keywords(text)
    cards = []
    for tp in TOPICS:
        if not _hits(tok, tp["keywords"]):
            continue
        points = []
        for kind, etype, ref, pdays in tp["points"]:
            pdays = pdays or days
            if kind == "incidents":
                st = db.incident_stats_bbox(CEUTA_BBOX, pdays)
                label = _point_label("incidents", lang)
                if st and st["count"]:
                    points.append({"label": f"{label} ({pdays} d)", "value": f"{st['count']} · {int(st['deaths'])} muertes"})
            elif kind == "region_incidents":
                st = db.incident_stats_iso3(MEDITERRANEO_W, pdays)
                label = _point_label("region_incidents", lang)
                if st and st["count"]:
                    points.append({"label": f"{label} ({pdays} d)", "value": f"{st['count']} · {int(st['deaths'])} muertes"})
            elif kind == "global_missing":
                st = db.incident_stats_iso3(None, pdays)
                label = _point_label("global_missing", lang)
                if st and st["count"]:
                    points.append({"label": f"{label} ({pdays} d)", "value": f"{st['count']} · {int(st['deaths'])} muertes"})
            elif kind == "stocks":
                s = db.last_stock(etype, ref)
                if s:
                    val = f"{int(s[0]):,}"
                    if lang == "es":
                        val = val.replace(",", ".")
                    points.append({"label": db.stock_label(etype, lang), "value": f"{val} · {s[1]}"})
            elif kind == "global_stock":
                v = db.global_stock(etype)
                if v:
                    val = f"{int(v):,}"
                    if lang == "es":
                        val = val.replace(",", ".")
                    points.append({"label": _point_label("global_stock", lang), "value": val})
        if points:
            cards.append({"id": tp["id"], "label": tp["label"][lang], "points": points,
                          "sources": [{"label": "IOM Missing Migrants Project", "url": "https://missingmigrants.iom.int/"},
                                      {"label": "UNHCR Refugee Data Finder", "url": "https://www.unhcr.org/refugee-statistics/"}]})
    return cards
