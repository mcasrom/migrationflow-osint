# MigrationFlow OSINT

Agregador open-source de **flujos migratorios y desplazamiento forzado** a escala global.
Eventos geolocalizados sobre desplazamiento interno (IDP), refugiados, solicitantes de
asilo y muertes/desapariciones en ruta, con severidad calculada y expiración automática.

Mapa: [Leaflet](https://leafletjs.com) + API [FastAPI](https://fastapi.tiangolo.com)
sobre **PostgreSQL 16 + PostGIS**, con PWA instalable.

## Fuentes

| Fuente | Tipo | URL | Frecuencia |
|---|---|---|---|
| UNHCR Refugee Data Finder | stock por país (refugiados, asilo, IDP, retornados) | `api.unhcr.org/population/v1` | anual (2 últimos años) |
| IDMC vía UNHCR | desplazamiento por conflicto | `api.unhcr.org/population/v1/idmc/` | anual |
| IOM DTM (HDX) | stock de IDP por país | CSV semanal en `data.humdata.org` | semanal |
| Missing Migrants Project (HDX) | incidentes con muertos/desaparecidos (con coordenadas) | CSV en `data.humdata.org` | semanal |

Todas las fuentes son **públicas y sin autenticación**.

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
    iom_dtm.py         stock IDP por país (CSV 37 MB)
    missing_migrants.py incidentes con coordenadas (CSV 7 MB)
    countries.py       centroides de países (data/countries_geo.json)
server.py              FastAPI + frontend estático
run.py                 orquestador del pipeline
scripts/pipeline.sh    envoltorio para cron
frontend/              Leaflet + PWA (oscuro, clústeres, heatmap, filtros)
data/countries_geo.json  centroides ISO3 (250 países)
```

### Ciclo de vida de un evento

- **Upsert** idempotente por `(source, source_id)`.
- **Severidad**: `info | warning | alert | critical` según umbrales por tipo
  (ver `SEVERITY_THRESHOLDS` en `src/config.py`).
- **Expiración**: cada fuente tiene un TTL (`SOURCE_TTL_DAYS`); los eventos
  activos vencidos se marcan `expired` en cada ejecución del pipeline.
- **Stock** = nivel país/región (centroide); **incidente** = evento puntual con coordenadas.

## Despliegue (VPS 2-4 GB, opción PM2)

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env            # ajusta credenciales de la BD
./venv/bin/python scripts/init_db.py

# API (puerto 8600)
pm2 start server.py --name migrationflow-api --interpreter ./venv/bin/python

# Pipeline (una vez manualmente y luego por cron)
./venv/bin/python run.py
crontab -e                       # p. ej. a las 02:30 UTC
30 2 * * * /home/deploy/migrationflow-osint/scripts/pipeline.sh
```

### Base de datos

Requiere PostgreSQL con PostGIS:

```sql
CREATE ROLE mf LOGIN PASSWORD '...';
CREATE DATABASE migrationflow OWNER mf;
CREATE EXTENSION IF NOT EXISTS postgis;
```

### API

| Ruta | Descripción |
|---|---|
| `/api/events?types=&min_level=&max_age_days=&bbox=&limit=` | eventos activos |
| `/api/summary` | totales por tipo y nivel |
| `/api/status` | estado por colector |
| `/health` | healthcheck |
| `/docs` | OpenAPI |

## Licencia

Open source. Datos: © UNHCR, IDMC, IOM (Missing Migrants Project y DTM), HDX.
