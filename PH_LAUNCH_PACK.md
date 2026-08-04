# Product Hunt Launch Pack — MigrationFlow OSINT

Launch target: **Aug 18, 2026** (0:00 PT, launch on Product Hunt). Prepared Aug 4, 2026.

- Product page: https://www.producthunt.com/products/migrationflow-osint
- Live site: https://migrationflow.viajeinteligencia.com
- Gallery assets: `assets/launch/*.png` (already captured from the real site)

---

## 1. Name & tagline

Name: **MigrationFlow OSINT** — *Live OSINT map of global migration flows & displacement*

Tagline candidates (pick one; PH shows it under the name):

1. Live OSINT map of global migration flows & forced displacement — from UNHCR, IOM, Frontex, IDMC & ReliefWeb.
2. Open-data map that tracks migration in near-real time and debunks migration myths.
3. Every point is a verified public-data event: see migration as it happens, twice a day.
4. Migration data, open and verifiable: incidents, routes, trends and hoax-checking on one map.
5. The global migration picture, rebuilt from public data twice a day.

**Recommended: #1** (factual, keyword-rich, matches the badge already on the site).

## 2. Description (long copy, ready to paste)

> **MigrationFlow OSINT** is an independent, open-data map of migration flows and forced displacement worldwide. Every point is a real event geolocated and classified by severity, collected automatically twice a day from official public sources — **UNHCR, IDMC, IOM (DTM & Missing Migrants Project), Frontex, Caminando Fronteras** and **ReliefWeb**.
>
> Migration is usually told through isolated figures. This project puts the pieces together in one reproducible, verifiable place so that journalists, researchers, humanitarian organizations and citizens can build their own picture.
>
> **What you can do**
> - Explore **5,000+ live events** — refugees, asylum-seekers, IDPs, displacement, deaths/missing on routes, arrivals and humanitarian alerts — filtered by type, severity and year.
> - Switch between **Historical / Current (90 days) / Trend** views and **play the evolution over time** with an animated timeline (oldest → today).
> - Compare **Frontex irregular-entry trends** (YTD vs. previous year) per country on a choropleth.
> - Check migration claims with the built-in **hoax verifier**: paste a headline and it cross-checks it against a curated set of debunked hoaxes (Maldita Migración, Newtral, UNHCR) and real events in the database.
> - **Export** the current view to **CSV or GeoJSON**.
> - Use it **offline as a PWA**, in **Spanish or English**.
>
> **Why it matters**
> Public data on migration exists but is scattered across agencies, formats and update cycles. MigrationFlow OSINT aggregates it transparently: open source, documented methodology, automatic expiry so the map always reflects current reality, and a clear "responsible use" policy — no surveillance, no profiling of individuals.
>
> **Stack**: Python/FastAPI + PostgreSQL/PostGIS + Leaflet PWA, self-hosted, updated twice a day. Data belongs to its sources; this is an independent, non-profit compilation.

## 3. Gallery (upload order matters — first image is the hero)

From `assets/launch/` (1280×800 desktop unless noted):

| # | File | Caption |
|---|---|---|
| 1 (hero) | `shot_map_en.png` | Live map — 5,000+ migration events geolocated and clustered |
| 2 | `shot_timeline.png` | Play the evolution over time: markers animate oldest → today |
| 3 | `shot_trend.png` | Frontex arrivals trend vs. previous year, per country |
| 4 | `shot_verify.png` | Hoax verifier: paste a claim, check it against debunked myths |
| 5 | `shot_charts.png` | Monthly deaths/missing and Frontex arrivals series |
| 6 | `shot_mobile.png` | PWA on mobile (works offline) |
| 7 | `shot_map_es.png` | Spanish UI — bilingual by default |

## 4. Maker comment (post as the maker, first thing on launch day)

> Hi Product Hunt 👋 I built **MigrationFlow OSINT** because migration data is everywhere but nowhere to be found — UNHCR, IDMC, IOM, Frontex and relief agencies publish excellent data, but in different formats, cycles and languages. This project aggregates all of it into one open, verifiable map, updated twice a day with no human intervention.
>
> A few things I'm proud of:
> - **5,000+ live events**, geolocated, classified by severity, with automatic expiry so nothing goes stale.
> - An **animated timeline** and Historical / Current / Trend views to see the phenomenon evolve.
> - A **hoax verifier**: paste any headline ("los menas reciben 20.000 €") and it tells you what the data and fact-checkers say.
> - 100% **open source**, non-profit, self-hosted, bilingual (ES/EN), works offline as a PWA.
>
> It's designed to be useful for journalists, researchers and humanitarians — and honest about its limits: figures are official estimates and some sources are conservative by definition.
>
> Happy to answer anything about the data, methodology or stack. ☕ If you find it useful, support the project or just share it with someone covering migration. Feedback welcome — I read everything.

## 5. FAQ (answers pre-written)

1. **Is it really "real time"?** No — it updates **twice a day** (automatic pipeline). We're explicit about it: freshness is shown on the map, and Frontex figures are monthly detections, not unique people.
2. **Where does the data come from?** Public sources only: UNHCR, IDMC, IOM DTM, IOM Missing Migrants Project, Frontex (ArcGIS), Caminando Fronteras, HDX and ReliefWeb. No private data.
3. **Is it affiliated with UNHCR/UN agencies?** No. It's an independent compilation; figures remain official estimates from the cited sources.
4. **How do you classify severity?** Per-category thresholds (e.g. volume of displaced or victims) → `info · warning · alert · critical`.
5. **Do events disappear?** Yes — events expire automatically when the source stops reporting them (TTL per source), so the map always reflects current activity.
6. **Is it free?** Yes, non-profit and open source. Data can be exported (CSV/GeoJSON) and the API is public.
7. **Does it track individuals?** No. Data is aggregated and anonymized; the project explicitly prohibits use for surveillance or profiling.
8. **Can I use the API?** Yes — FastAPI with interactive docs at `/docs`; `/api/events`, `/api/summary`, `/api/country/{iso3}`, `/api/trends`, `/api/charts`, `/api/verify`.

## 6. Topics (PH topic tags)

- Open Source · Data & Analytics · Developer Tools · Maps · Artificial Intelligence *(only if tagging AI: the verifier is NOT AI — avoid the AI topic to prevent a bad fit; use: Data Visualization, Journalism, OSINT)*
- Recommended: **Open Source, Data & Analytics, Maps, Data Visualization, Journaling** *(final: Open Source, Data & Analytics, Maps, Productivity → choose what fits)*

## 7. Day-1 vote plan (checklist)

- [ ] **D-2**: upload gallery, description and tagline to the PH draft; prepare maker comment.
- [ ] **D-1**: post to X/Telegram/Reddit **only after** the hunt is live (link to the PH page).
- [ ] **Launch (0:00 PT)**: publish; immediately post the **maker comment**.
- [ ] **0–2 h**: share with first circle (friends, OSINT/data communities, Discord/Telegram groups, DM a few early adopters). The first 2 hours decide the ranking.
- [ ] **Morning (EU)**: post in r/migrationpolicy, r/openstreetmap, r/dataisbeautiful, r/gis, r/datasets + X thread with the 7 screenshots.
- [ ] **Afternoon (US)**: Show HN (link to repo), second X wave with different angle (hoax verifier).
- [ ] **Reply to every comment** within the hour — engagement is scored.
- [ ] **D+1**: thank-you comment; log traffic from `/analytics` (GoAccess, basic auth) and UptimeRobot.
- Keep the **kofi button** visible: non-profit projects convert interest into support.

## 8. Companion posts (drafts included)

### X / Telegram thread (paste, adjust hashtags)
1/ Migration is usually told through isolated figures. We rebuilt the picture from public data, on one open map. 🗺️ MigrationFlow OSINT — every point is a verified event from UNHCR, IOM, Frontex, IDMC & ReliefWeb, updated twice a day. [link]
2/ 5,000+ live events: refugees, asylum, IDPs, deaths/missing on routes, arrivals, alerts — classified by severity, expiring automatically when sources stop reporting.
3/ ▶️ Play the evolution: watch the map rebuild from 2024 to today, or switch Historical → Current (90 d) → Trend (Frontex vs last year).
4/ 🛡️ Paste any claim ("los menas reciben 20.000 €") and the hoax verifier tells you what fact-checkers and the data say.
5/ 100% open source, non-profit, self-hosted, ES/EN, offline PWA. If it helps you report better, share it. ☕ [link] #migration #OSINT #opendata #dataviz

### Reddit (draft, adjust title per sub)
**Title (r/dataisbeautiful / r/gis / r/openstreetmap / r/datasets):** "MigrationFlow OSINT — an open-source live map of 5,000+ migration events from UNHCR, IOM, Frontex, IDMC & ReliefWeb [OC, data & code public]"
**Body:** Short pitch + link + note: data public via API, code on GitHub, updated twice daily, ES/EN, non-profit. On r/migrationpolicy add: "useful for researchers and policymakers; hoax verifier built in." Use `shot_map_en.png` as static image.

### Show HN
**Title:** Show HN: MigrationFlow OSINT – open-source live map of migration from UNHCR/IOM/Frontex data
**Body:** What it does, why (scattered public data), architecture (FastAPI + PostGIS + Leaflet PWA), what's open (code, API, data), known limits (twice-daily, Frontex detections ≠ people, some sources conservative). Link repo + demo.

## 9. Media & links for the PH page

- Website: https://migrationflow.viajeinteligencia.com
- GitHub: https://github.com/mcasrom/migrationflow-osint
- API docs: https://migrationflow.viajeinteligencia.com/docs
- Support: https://ko-fi.com/m_castillo
- Contact: migrationflow@viajeinteligencia.com
- Gallery images: `assets/launch/` in the repo (same files to upload).

---

## Post-launch follow-ups (P4 remainder)

- [ ] 30s demo GIF/video (capture the timeline animation) — pending.
- [ ] Google re-crawl: submit sitemap again + monitor indexing (Search Console).
- [ ] UptimeRobot + GoAccess: check traffic spike on launch day.
