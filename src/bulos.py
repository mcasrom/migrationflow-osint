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
import socket
import unicodedata
from ipaddress import ip_address

import httpx

from src import db
from src.config import HTTP_TIMEOUT, USER_AGENT


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return re.sub(r"[\u0300-\u036f]+", "", s)


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _norm(s)) if len(t) >= 3]


def _hits(tokens: list[str], keywords: list[str], raw_norm: str = "") -> list[str]:
    kw = sorted({_norm(k) for k in keywords}, key=len, reverse=True)
    hits = []
    for k in kw:
        if " " in k:
            if raw_norm and k in raw_norm:   # frase: aparece contigua en el texto
                hits.append(k)
            continue
        for t in tokens:
            if t == k:
                hits.append(k)
                break
            if len(k) >= 4 and abs(len(t) - len(k)) <= 3 and (t.startswith(k) or k.startswith(t)):
                hits.append(k)
                break
    return hits


# ── Bulos recurrentes desmentidos (curados) ──────────────────────────
BULOS = [
    {
        "id": "ayudas-400-900",
        "keywords": ["400", "900", "ayuda", "subvencion", "cobran", "ingreso", "prestacion", "renta"],
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
    {
        "id": "imv-sin-requisitos",
        "keywords": ["imv", "ingreso minimo vital", "renta garantizada", "cobran el imv"],
        "title": {"es": "Los inmigrantes cobran el Ingreso Mínimo Vital (IMV) sin cumplir requisitos",
                  "en": "Migrants receive the Minimum Vital Income without meeting requirements"},
        "claim": {"es": "Falso: el IMV exige cumplir requisitos (residencia, vulnerabilidad, patrimonio) que aplican a toda la ciudadanía.",
                  "en": "False: the IMV requires meeting conditions (residence, vulnerability, assets) that apply to all citizens."},
        "evidence": {"es": "El IMV es una prestación de la Seguridad Social accesible a cualquier residente que cumpla los requisitos de vulnerabilidad; no se concede por nacionalidad y cada solicitud se revisa individualmente.",
                     "en": "IMV is a social-security benefit open to any resident meeting vulnerability criteria; it is not granted by nationality and each application is assessed individually."},
        "sources": [
            {"label": "Seguridad Social · IMV", "url": "https://www.seg-social.es/"},
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
        ],
    },
    {
        "id": "retorno-voluntario",
        "keywords": ["retorno voluntario", "vuelta a su pais", "pagan por irse", "pagan por volver",
                     "se vayan a su pais", "pago por marcharse"],
        "title": {"es": "España paga miles de euros a los inmigrantes para que se marchen",
                  "en": "Spain pays migrants thousands of euros to leave"},
        "claim": {"es": "La ayuda al retorno voluntario existe pero es voluntaria, menor y sujeta a requisitos; las cifras virales son falsas.",
                  "en": "Voluntary-return support exists but is voluntary, modest and conditional; viral figures are false."},
        "evidence": {"es": "El programa de apoyo al retorno voluntario financia el viaje de vuelta y, en su caso, una pequeña ayuda de reintegración muy inferior a las cifras difundidas; es un derecho del interesado, no un pago por expulsarse.",
                     "en": "Voluntary-return support funds the journey home and, where applicable, a small reintegration allowance far below circulated figures; it is a right of the applicant, not a payment to leave."},
        "sources": [
            {"label": "Ministerio de Inclusión", "url": "https://www.inclusion.gob.es/"},
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
        ],
    },
    {
        "id": "vivienda-prioridad",
        "keywords": ["vivienda publica", "vpo", "proteccion oficial", "piso protegido",
                     "prioridad de acceso", "vivienda protegida", "cupo de vivienda"],
        "title": {"es": "Los inmigrantes tienen prioridad en la vivienda pública u ocupan pisos protegidos",
                  "en": "Migrants have priority access to public housing or squat in protected flats"},
        "claim": {"es": "No hay cupos ni prioridad por nacionalidad en el acceso a vivienda protegida.",
                  "en": "There are no quotas or nationality-based priority rules for protected housing."},
        "evidence": {"es": "El acceso a vivienda protegida se regula por empadronamiento, renta y situación personal, no por nacionalidad; la ocupación ilegal es un delito tipificado con independencia de la procedencia.",
                     "en": "Access to protected housing depends on registration, income and personal situation, not nationality; illegal squatting is a criminal offence regardless of origin."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "Newtral", "url": "https://www.newtral.es/"},
        ],
    },
    {
        "id": "empleo-quitan",
        "keywords": ["quitan el trabajo", "roban el empleo", "quitan los puestos",
                     "no quieren trabajar", "vienen a vivir de", "quitan trabajo"],
        "title": {"es": "Los inmigrantes quitan el trabajo a los españoles o viven de las ayudas sin trabajar",
                  "en": "Migrants steal jobs from Spaniards or live on benefits without working"},
        "claim": {"es": "No hay evidencia de que la inmigración reduzca el empleo de la población nativa.",
                  "en": "There is no evidence that immigration reduces native employment."},
        "evidence": {"es": "Los estudios económicos no muestran una relación causal entre inmigración y desempleo local; los inmigrantes ocupan con frecuencia nichos con vacantes (agricultura, cuidados, hostelería) y cotizan al sistema.",
                     "en": "Economic studies show no causal link between immigration and local unemployment; migrants often fill labour shortages (farming, care, hospitality) and contribute to the system."},
        "sources": [
            {"label": "FEDEA", "url": "https://www.fedea.net/"},
            {"label": "OIT", "url": "https://www.ilo.org/"},
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
        ],
    },
    {
        "id": "inmigracion-criminalidad",
        "keywords": ["criminalidad", "delincuencia", "delitos", "violaciones", "agresiones",
                     "seguridad ciudadana", "oleada de"],
        "title": {"es": "La inmigración dispara la criminalidad",
                  "en": "Immigration drives up crime"},
        "claim": {"es": "Los datos oficiales no respaldan esa correlación; la criminalidad depende de factores socioeconómicos.",
                  "en": "Official data do not support that correlation; crime depends on socio-economic factors."},
        "evidence": {"es": "Las estadísticas del Ministerio del Interior y Eurostat no constatan una relación causal entre inmigración y delitos; los bulos suelen generalizar casos aislados.",
                     "en": "Interior Ministry and Eurostat statistics show no causal link between immigration and crime; hoaxes usually generalise isolated cases."},
        "sources": [
            {"label": "Ministerio del Interior", "url": "https://www.interior.gob.es/"},
            {"label": "Eurostat", "url": "https://ec.europa.eu/eurostat/"},
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
        ],
    },
    {
        "id": "sanidad-saturada",
        "keywords": ["saturan la sanidad", "colapsan la sanidad", "sanidad gratis", "tarjeta sanitaria",
                     "usar la sanidad", "sanidad para extranjeros"],
        "title": {"es": "Los inmigrantes saturan la sanidad pública y la usan gratis",
                  "en": "Migrants overwhelm the public health system and use it for free"},
        "claim": {"es": "El uso sanitario de los inmigrantes es similar o inferior al de la población general.",
                  "en": "Migrants' health-system use is similar to or lower than the general population's."},
        "evidence": {"es": "Los estudios sobre utilización de servicios sanitarios muestran un consumo comparable o inferior al de la población autóctona en muchos casos; el derecho a asistencia se regula por residencia y padrón, no por nacionalidad.",
                     "en": "Studies of health-service use show comparable or lower consumption than the native population in many cases; the right to care depends on residence and registration, not nationality."},
        "sources": [
            {"label": "Ministerio de Sanidad", "url": "https://www.sanidad.gob.es/"},
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
        ],
    },
    {
        "id": "pateras-subvencionadas",
        "keywords": ["pateras", "subvencionad", "pagan por venir", "vienen pagados",
                     "pagan por llegar", "migracion subvencionada"],
        "title": {"es": "Las pateras y la inmigración están subvencionadas",
                  "en": "Boats and immigration are government-funded"},
        "claim": {"es": "No hay subvención a la inmigración irregular ni pagos por llegar en patera.",
                  "en": "There is no funding for irregular migration nor payments for arriving by boat."},
        "evidence": {"es": "El tránsito irregular no está financiado por el Estado; quienes llegan pagan a redes de tráfico de personas. Las organizaciones humanitarias rescatan y asisten, no 'pagan' por la llegada.",
                     "en": "Irregular transit is not state-funded; those who arrive pay people-smuggling networks. Humanitarian organisations rescue and assist — they do not pay people to come."},
        "sources": [
            {"label": "Maldita.es · Migración", "url": "https://maldita.es/migracion/"},
            {"label": "Guardia Civil", "url": "https://www.guardiacivil.es/"},
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
            ("route_arrivals", None, "ROUTE_WMED", None),
            ("cf_total", None, None, None),
        ],
    },
    {
        "id": "mediterraneo",
        "keywords": ["patera", "mediterrane", "naufragio", "rescate", "ruta"],
        "label": {"es": "Ruta del Mediterráneo", "en": "Mediterranean route"},
        "points": [
            ("region_incidents", "missing", "MEDITERRANEO_W", 365),
            ("global_missing", None, None, 365),
            ("route_arrivals", None, "ROUTE_CMED", None),
            ("cf_total", None, None, None),
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


# ── Verificación por URL (share-link) ────────────────────────────
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_MAX_FETCH_BYTES = 400_000
_MAX_REDIRECTS = 3

_OG_TITLE_RE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_OG_DESC_RE = re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', re.IGNORECASE | re.DOTALL)


def is_url(text: str) -> bool:
    return bool(_URL_RE.match((text or "").strip()))


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return bool(infos)


def _clean_meta(raw: str) -> str:
    raw = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", raw).strip()


def fetch_claim(url: str, max_bytes: int = _MAX_FETCH_BYTES) -> dict | None:
    """Descarga una URL pública y extrae título + descripción para verificar un claim.

    Con guardia anti-SSRF: rechaza hosts que resuelvan a IPs privadas/loopback y
    valida cada redirección. Devuelve None si no es segura o no hay texto útil.
    """
    url = (url or "").strip()
    if not is_url(url):
        return None
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        try:
            host = httpx.URL(current).host
        except ValueError:
            return None
        if not host or not _is_public_host(host):
            return None
        try:
            r = httpx.get(current, timeout=HTTP_TIMEOUT, follow_redirects=False,
                          headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
        except httpx.HTTPError:
            return None
        if r.is_redirect and r.headers.get("location"):
            current = str(httpx.URL(current).join(r.headers["location"]))
            continue
        break
    html = r.text[:max_bytes]
    title = ""
    for pat in (_OG_TITLE_RE, _TITLE_RE, _META_DESC_RE):
        m = pat.search(html)
        if m:
            title = _clean_meta(m.group(1))
            break
    desc = ""
    for pat in (_OG_DESC_RE, _META_DESC_RE):
        m = pat.search(html)
        if m:
            desc = _clean_meta(m.group(1))
            break
    return {"title": title, "description": desc, "final_url": current}


def check_bulos(text: str) -> list[dict]:
    """Devuelve los bulos curados cuyas keywords coinciden con `text`."""
    if not text:
        return []
    tok = _match_keywords(text)
    raw_norm = _norm(text)
    results = []
    for b in BULOS:
        hits = _hits(tok, b["keywords"], raw_norm)
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
        "route_arrivals": {"es": "Entradas irregulares este mes (Frontex)",
                           "en": "Irregular arrivals this month (Frontex)"},
        "cf_total": {"es": "Víctimas hacia el Estado español (CF, último informe)",
                     "en": "Victims heading to Spain (CF, latest report)"},
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
            elif kind == "route_arrivals":
                r = db.route_arrivals_latest(ref)
                if r:
                    when = r["reported_at"][:7]
                    points.append({"label": f"{_point_label('route_arrivals', lang)} ({r['name']})",
                                   "value": f"{int(r['value']):,} · {when}"})
            elif kind == "cf_total":
                rep = db.cf_report()
                if rep:
                    val = f"{int(rep['total']):,}"
                    if lang == "es":
                        val = val.replace(",", ".")
                    points.append({"label": f"{_point_label('cf_total', lang)}",
                                   "value": f"{val} · {rep['period']}"})
        if points:
            sources = [{"label": "IOM Missing Migrants Project", "url": "https://missingmigrants.iom.int/"},
                       {"label": "UNHCR Refugee Data Finder", "url": "https://www.unhcr.org/refugee-statistics/"}]
            if tp["id"] in ("ceuta", "mediterraneo"):
                sources.append({"label": "Frontex · Detections of IBCs", "url": "https://www.frontex.europa.eu/"})
                sources.append({"label": "Caminando Fronteras", "url": "https://caminandofronteras.org/"})
            cards.append({"id": tp["id"], "label": tp["label"][lang], "points": points,
                          "sources": sources})
    return cards
