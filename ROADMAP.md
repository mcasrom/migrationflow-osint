# MigrationFlow OSINT — Hoja de ruta (way ahead)

Documento operativo para **continuar el proyecto desde el propio servidor**.
Este repo vive en el Hetzner (`/home/deploy/migrationflow-osint`) y se publica en
[GitHub](https://github.com/mcasrom/migrationflow-osint).

Producción: **https://migrationflow.viajeinteligencia.com**

---

## 1. Estado actual (agosto 2026)

- **En vivo y funcionando**: API en `:8600` (PM2 `migrationflow-api`), frontend Leaflet PWA, HTTPS.
- **7738 eventos activos**: UNHCR 451 · IDMC 80 · IOM DTM 21 · Missing Migrants 7092 ·
  Frontex entradas 75 · Frontex rutas 6 · Caminando Fronteras 5 · News 8.
- **Pipeline automático**: cron `15 2,14 * * *` → `scripts/pipeline.sh` (02:15 y 14:15 UTC, sin intervención)
  con **7 colectores**: UNHCR, IDMC, IOM DTM, Missing Migrants, Frontex, Caminando Fronteras, News.
- **Frontend**: mapa con clústeres por tipo, niveles, heatmap, **tema claro/oscuro persistente**,
  filtro por año (2023–2026, afecta a mapa **y summary**), **choropleth por país**, **popup de país al hacer click** (últimos
  365 días + delta vs. período previo, click en choropleth y botón en popups de marcadores),
  capa de rutas migratorias, **botón de compartir (Web Share + portapapeles)**, funnel de
  bienvenida, i18n ES/EN, pestañas Datos / Fuentes / **Acerca de**, **PWA instalable (SW
  registrado, pre-cache, `beforeinstallprompt`)**, export CSV/GeoJSON, botón Ko-fi, pestaña
  Fuentes (metodología, estado, contacto).
- **Verificador de bulos** (`/api/verify`): 6 bulos recurrentes curados (ayudas 400-900 €, menas 20.000 €,
  avalancha en la valla, patera=delincuencia, paro sin cotizar, no pagan impuestos) con evidencia y fuentes
  verificadoras (Maldita, Newtral, ACNUR); sección *¿Es un bulo?* en el panel y enlace desde popups de noticias.
- **Tarjeta de contexto por datos** (`/api/context`): dado el título de un evento, genera tarjetas con cifras
  reales de la BD (incidentes MMP por zona/región/mundo, stocks UNHCR) para tópicos Ceuta-Melilla,
  Ruta del Mediterráneo y Asilo; se inyecta en el popup de noticias.
- **Alertas push por zona**: suscripción Web Push (VAPID) por región (global/España/Marruecos/Mediterráneo);
  `scripts/check_alerts.py` (cron `15 */6 * * *`) detecta picos de incidentes (≥2 y ratio 1.5 vs. semana previa)
  y noticias sobre temas con bulos, con tabla `alert_log` de dedupe.
- **API de país**: `GET /api/country/{iso3}?days=365` → `{name, affected, stocks, activity, delta}`.
- **Frontex (entradas)**: colector automático sobre el ArcGIS FeatureServer público de detecciones de cruces
  irregulares (IBC). Ingesta **entradas anuales por país de origen** (`arrivals`, años completos recientes +
  parcial actual) y **totales mensuales por ruta** (`arrivals_route`). Nota metodológica: Frontex cuenta
  *detecciones* (una persona puede contarse varias veces).
- **Caminando Fronteras (víctimas)**: colector curado que localiza el último informe del *Monitoreo del
  Derecho a la Vida* vía el RSS del sitio y parsea las víctimas por ruta hacia España (`cf_victims`;
  Atlántica, Argelia, Estrecho, Alborán, Terrestre). Cada nuevo informe expira el anterior. La cifra es una
  **estimación de la ONG** (incluye desaparecidos) y **no es comparable 1:1 con IOM MMP** — se muestra como
  fuente complementaria con su metodología. Escape hatch: `data/cf_override.json` para corregir cifras a mano.
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
      filtro `year` (ahora también en el summary); falta la comparativa en el choropleth o una vista delta.
- [ ] **Panel de gráficos**: pestaña con serie mensual de incidentes y top países afectados.
- [ ] **Geocoding fino para news**: localizar subregiones/ciudades (hoy centroide de país).
- [ ] **Ampliar dataset de bulos** a más claims (hoy 6 curados) y añadir verificación por URL/claim compartido.
- [ ] **Capa Frontex con tendencia**: serie mensual de entradas por ruta (hoy el dato del mes actual por ruta
      y anual por país); podría alimentar el modo tendencia.

### P2 — Experiencia
- [ ] **Línea de tiempo animada**: botón *play* que anima los marcadores por fecha (2024 → hoy).
- [ ] **Capas Histórico / Actual / Tendencia**: control segmentado sobre el mismo mapa.
- [ ] Self-host de Leaflet y plugins (hoy desde CDN unpkg) para eliminar dependencia externa.
- [x] Open Graph / meta description completas para compartir en redes (`og.png` 1200×630 + Twitter card;
      preview de icono y RRSS en `/preview.html`, no indexado).

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
- Service worker con **network-first para assets** (SW v12): tras un deploy basta recargar una vez; las
  cachés viejas se purgan al activar. Las suscripciones push quedan inválidas si se regeneran las claves VAPID
  (limpiar `push_subscriptions`).
- **Muertes = IOM MMP (conservador) + Caminando Fronteras (estimación)**: dos fuentes con metodología distinta.
  MMP registra incidentes confirmados (cifra conservadora); CF estima incluyendo desaparecidos (cifra mayor).
  Se muestran como capas separadas (`missing` y `cf_victims`) con su nota metodológica para no mezclarlas.
- **Caminando Fronteras**: depende del formato del post (parseo con regex). Si un informe cambia el texto y
  falla el parseo, el colector registra el error y conserva los datos anteriores (expiran por TTL de 210 días);
  se puede corregir manualmente creando `data/cf_override.json` (ver `cf_override.json.example` si se crea).
- **Frontex**: el FeatureServer conserva ~36 meses; los años completos se ingieren solo mientras el servicio
  los tenga íntegros (el parcial actual siempre). Cuando un año deja de estar completo, la fila expira sola.
