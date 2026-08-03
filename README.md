# MigrationFlow OSINT

Agregador open-source de **flujos migratorios y desplazamiento forzado** a escala global.
Eventos geolocalizados sobre desplazamiento interno (IDP), refugiados, solicitantes de asilo,
muertes/desapariciones en ruta y alertas humanitarias, con severidad calculada y **expiración automática**.

- **Mapa en vivo**: https://migrationflow.viajeinteligencia.com
- **API**: FastAPI · **BD**: PostgreSQL 16 + PostGIS · **Frontend**: Leaflet (PWA)
- **Repo público**: código abierto, fuentes y criterios documentados

## Características

- Mapa Leaflet con **clústeres por categoría**, niveles de severidad (`info · warning · alert · critical`),
  **heatmap** de incidentes y **tema oscuro/claro**.
- **Choropleth por país** agregando personas afectadas, con selector de año (2023–2026) para
  comparar períodos históricos.
- **Filtro temporal por año** y **capa de rutas migratorias** principales (aprox.).
- **Funnel de bienvenida** con estadísticas en vivo para nuevos visitantes.
- **i18n ES/EN** con selector de idioma.
- **Export** a CSV y GeoJSON.
- **PWA** instalable (service worker, manifest, icono).
- Pestaña **Fuentes**: metodología, estado en vivo de los colectores, contacto y aviso legal.

## Fuentes

Todas **públicas y sin autenticación**.

| Fuente | Tipo | URL | Frecuencia |
|---|---|---|---|
| UNHCR Refugee Data Finder | stock por país (refugiados, asilo, IDP) | `api.unhcr.org/population/v1` | anual (2 últimos años) |
| IDMC vía UNHCR | desplazamiento interno por conflicto | `api.unhcr.org/population/v1/idmc/` | anual |
| IOM DTM (HDX) | stock de IDP por país | CSV semanal en `data.humdata.org` | semanal |
| Missing Migrants Project (HDX) | incidentes con muertos/desaparecidos (coordenadas) | CSV en `data.humdata.org` | semanal |
| Frontex | entradas irregulares anuales por país y mensuales por ruta | ArcGIS REST `services9.arcgis.com/dujMioKFm7jZpirQ/.../DetectionsOfIBCs` | semanal (detecciones, no personas únicas) |
| Caminando Fronteras | víctimas mortales en rutas hacia España (curado) | RSS `caminandofronteras.org/search/monitoreo/feed/rss2/` | cada informe (override en `data/cf_override.json`) |
| ReliefWeb | noticias y alertas humanitarias | RSS `reliefweb.int/updates/rss.xml` | diaria |

## Arquitectura

```
src/
  config.py            constantes, umbrales de severidad, TTL
  logging.py           log a fichero rotatorio + consola
  models.py            Event (dataclass)
  db.py                pool, esquema, upsert, expiración, consultas API
  collectors/
    base.py            BaseCollector (ejecución + registro de runs)
    unhcr.py           stock por país (coo_all / coa_all)
    idmc.py            desplazamiento por conflicto
    iom_dtm.py         stock IDP por país (CSV semanal)
    missing_migrants.py incidentes con coordenadas (CSV)
    frontex.py          entradas irregulares (anual por país, mensual por ruta)
    caminando_fronteras.py víctimas en rutas hacia España (RSS + parse curado)
    news.py            noticias ReliefWeb (RSS + geolocalización)
    countries.py       centroides y resolución ISO3 (data/countries_geo.json)
server.py              FastAPI + frontend estático
run.py                 orquestador del pipeline
scripts/pipeline.sh    envoltorio para cron
frontend/              Leaflet + PWA (clústeres, heatmap, choropleth, rutas, i18n)
data/countries_geo.json  centroides ISO3 (250 países)
```

### Ciclo de vida de un evento

- **Upsert** idempotente por `(source, source_id)`.
- **Severidad**: `info | warning | alert | critical` según umbrales por tipo (`SEVERITY_THRESHOLDS`).
- **Expiración**: TTL por fuente (`SOURCE_TTL_DAYS`); los activos vencidos se marcan `expired` en cada corrida.
- **Stock** = nivel país/región (centroide); **incidente** = evento puntual con coordenadas.
- **ISO3**: resuelto en ingesta (`match_country_iso3`) para todos los eventos.

## API

| Ruta | Descripción |
|---|---|
| `/api/events?types=&min_level=&max_age_days=&bbox=&year=&limit=` | eventos activos (filtros combinables) |
| `/api/summary` | totales por tipo, nivel y suma de valor |
| `/api/country/{iso3}?days=` | resumen por país (stocks, entradas Frontex, actividad) |
| `/api/arrivals/series?country=&months=` | serie mensual de entradas Frontex (global o por país) |
| `/api/trends` | tendencia de entradas por país (YTD actual vs. mismo periodo previo, % variación) |
| `/api/charts` | datos del panel de gráficos (incidentes mensuales, entradas mensuales, top países) |
| `/api/context?q=&lang=` | tarjetas de contexto (cruza bulos + datos reales) para un claim |
| `/api/verify` (POST `{q, lang}`) | verificador de bulos: matches curados + eventos reales + fact-checkers |
| `/api/status` | estado por colector + tipos de evento |
| `/api/push/*` | suscripción/alta VAPID para notificaciones push |
| `/health` | healthcheck |
| `/docs` | OpenAPI interactivo |

Ejemplo:
```bash
# Incidentes de 2024 de nivel alert o superior, en Centroamérica
curl "https://migrationflow.viajeinteligencia.com/api/events?min_level=alert&year=2024&bbox=-92,7,-77,18"

# Entradas irregulares (Frontex) y stocks para Afganistán
curl "https://migrationflow.viajeinteligencia.com/api/country/AFG?days=365"

# Tarjeta de contexto para una frase
curl "https://migrationflow.viajeinteligencia.com/api/context?q=patera%20naufragio"
```

## Despliegue (VPS, opción PM2)

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env            # ajusta credenciales de la BD
./venv/bin/python scripts/init_db.py

# API (puerto 8600)
pm2 start server.py --name migrationflow-api --interpreter ./venv/bin/python
pm2 save

# Pipeline (una vez manualmente y luego por cron)
./venv/bin/python run.py
crontab -e                      # p. ej. dos veces al día
15 2,14 * * * /home/deploy/migrationflow-osint/scripts/pipeline.sh
```

### Base de datos

Requiere PostgreSQL con PostGIS:

```sql
CREATE ROLE mf LOGIN PASSWORD '...';
CREATE DATABASE migrationflow OWNER mf;
CREATE EXTENSION IF NOT EXISTS postgis;
```

## Operación y roadmap

- **Roadmap / way ahead** (estado, comandos, próximos pasos): [ROADMAP.md](ROADMAP.md).
- Contacto: migrationflow@viajeinteligencia.com

## Licencia

Open source. Los datos pertenecen a sus fuentes (© UNHCR, IDMC, IOM, HDX, Frontex, Caminando Fronteras,
ReliefWeb); este proyecto es una recopilación independiente con fines informativos y de análisis.
Las cifras de Frontex son **detecciones** (no personas únicas) y las de Caminando Fronteras incluyen
personas desaparecidas, por lo que no son comparables 1:1 entre sí ni con IOM MMP.
