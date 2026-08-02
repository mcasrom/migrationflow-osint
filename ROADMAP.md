# MigrationFlow OSINT — Hoja de ruta (way ahead)

Documento operativo para **continuar el proyecto desde el propio servidor**.
Este repo vive en el Hetzner (`/home/deploy/migrationflow-osint`) y se publica en
[GitHub](https://github.com/mcasrom/migrationflow-osint).

Producción: **https://migrationflow.viajeinteligencia.com**

---

## 1. Estado actual (agosto 2026)

- **En vivo y funcionando**: API en `:8600` (PM2 `migrationflow-api`), frontend Leaflet PWA, HTTPS.
- **7651 eventos activos**: UNHCR 451 · IDMC 80 · IOM DTM 21 · Missing Migrants 7092 · News 7.
- **Pipeline automático**: cron `15 2,14 * * *` → `scripts/pipeline.sh` (02:15 y 14:15 UTC, sin intervención).
- **Frontend**: mapa con clústeres por tipo, niveles, heatmap, tema oscuro, filtro por año
  (2023–2026), **choropleth por país**, **popup de país al hacer click** (últimos 365 días +
  delta vs. período previo, click en choropleth y botón en popups de marcadores), capa de rutas
  migratorias, funnel de bienvenida, i18n ES/EN, pestañas Datos / Fuentes / **Acerca de**,
  export CSV/GeoJSON, botón Ko-fi, pestaña Fuentes (metodología, estado, contacto).
- **API de país**: `GET /api/country/{iso3}?days=365` → `{name, affected, stocks, activity, delta}`.
- **Semántica de datos corregida** (commit `3a91a80`): `affected` y `sum_value` global usan
  **último snapshot por tipo** (sin doble conteo de años consecutivos ni mezclar muertes);
  etiqueta de asilo = *stock pendiente*; nota metodológica de IOM MMP en el popup.

## 2. Cómo se trabaja en el proyecto (flujo)

1. **Editar en staging local** (`/tmp/opencode/mf/`, estructura espejo del deploy).
2. **Sincronizar** al servidor:
   ```bash
   rsync -az --exclude venv --exclude .env --exclude .git --exclude data \
     --exclude logs --exclude '*.pyc' --exclude '__pycache__' --exclude 'dbg_*' \
     /tmp/opencode/mf/ deploy@178.105.80.193:/home/deploy/migrationflow-osint/
   ```
3. **Probar** colectores / pipeline:
   ```bash
   ./venv/bin/python run.py --collectors news          # un colector
   ./venv/bin/python run.py                            # todos
   ```
4. **Reiniciar API** (solo si cambió backend):
   ```bash
   pm2 restart migrationflow-api --update-env
   ```
5. **Commit + push** (el push publica en GitHub, repo público):
   ```bash
   git add -A && git commit -m "mensaje" && git push origin main
   ```

## 3. Operación en el servidor

| Tarea | Comando |
|---|---|
| Estado PM2 | `pm2 status \| grep migrationflow` |
| Logs API | `pm2 logs migrationflow-api --lines 50` |
| Logs pipeline | `tail -n 50 /home/deploy/migrationflow-osint/logs/pipeline.log` |
| Pipeline manual | `cd /home/deploy/migrationflow-osint && ./venv/bin/python run.py` |
| Cron | `crontab -l` (editar con `crontab -e`) |
| BD | `psql migrationflow` (rol `mf`, password en `.env`) |
| Healthcheck | `curl http://127.0.0.1:8600/health` |

### Puntos de atención (notas operativas)

- **.env** contiene credenciales (`DB_PASSWORD`); **no** está en git (`.gitignore`). Hay `.env.example`.
- **ReliefWeb** (colector `news`) responde `406` si no se usa un User-Agent de navegador y cabecera
  `Accept` correcta — ya gestionado en `src/collectors/news.py`.
- **Missing Migrants**: retén de **36 meses** (`MMP_RETENTION_MONTHS`); los incidentes expiran al salir de esa ventana.
  Cifra **conservadora** (solo incidentes confirmados); las ONG (p. ej. Caminando Fronteras) reportan más
  muertes — el popup de país muestra nota aclaratoria.
- **News**: TTL de **14 días** (`SOURCE_TTL_DAYS`); son puntos de actualidad, no stock.
- `deploy.sh` pasa `--host/--port` a `server.py`, pero `server.py` toma `SERVER_HOST/PORT` de `.env`
  (los argumentos se ignoran; inofensivo).

## 4. Hoja de ruta pendiente

Priorizada (P1 = mayor valor/esfuerzo).

### P1 — Siguiente iteración
- [ ] **Modo tendencia**: color por % de cambio respecto al año anterior (▲▼, rojo/verde). Ya existe el
      filtro `year`; falta la comparativa en el choropleth o una vista delta.
- [ ] **Panel de gráficos**: pestaña con serie mensual de incidentes y top países afectados.
- [ ] **Geocoding fino para news**: localizar subregiones/ciudades (hoy centroide de país).
- [ ] **Fuente complementaria de muertes** (opcional, desactivada por defecto): ingestar Caminando Fronteras
      u otra fuente con contraste metodológico explícito, en lugar de depender solo de IOM MMP.

### P2 — Experiencia
- [ ] **Línea de tiempo animada**: botón *play* que anima los marcadores por fecha (2024 → hoy).
- [ ] **Capas Histórico / Actual / Tendencia**: control segmentado sobre el mismo mapa.
- [ ] Self-host de Leaflet y plugins (hoy desde CDN unpkg) para eliminar dependencia externa.
- [ ] Open Graph / meta description completas para compartir en redes.

### P3 — Calidad y automatización
- [ ] Tests automatizados (unittest de `src.db`, `countries`, colectores con fixtures).
- [ ] CI en GitHub Actions (lint + tests) para proteger `main`.
- [ ] Alerta visible en el frontend si un colector falla 2+ corridas seguidas (hoy solo estado en "Fuentes").
- [ ] Export GeoJSON de agregación por país (para descargar el choropleth).
- [ ] Evitar doble conteo en el choropleth cuando el filtro de año es "todos" (hoy suma todos los snapshots
      del período por tipo por país; el popup ya no lo hace).

## 5. Problemas conocidos

- **Sampling CPU headless**: no aplica.
- El funnel de bienvenida se guarda en `localStorage` (`mf_intro_seen`) — al probar cambios, limpiar
  el sitio o usar ventana privada.
- Service worker con cache-first para assets: tras un deploy, la primera carga puede servir JS viejo;
  la navegación ya es network-first (SW v8).
- **Muertes = IOM MMP (conservador)**: no refleja estimaciones tipo Caminando Fronteras; comunicado vía
  nota en el popup de país.
