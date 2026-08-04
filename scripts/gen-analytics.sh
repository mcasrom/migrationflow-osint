#!/usr/bin/env bash
set -euo pipefail

LOG_DIR=/var/log/nginx
DEDICATED=$LOG_DIR/migrationflow.access.log
ANALYTICS=/home/deploy/migrationflow-osint/analytics
FILTERED=$ANALYTICS/migrationflow-filtered.log
OUT=$ANALYTICS/index.html

mkdir -p "$ANALYTICS"

# Solo peticiones de migrationflow.viajeinteligencia.com (histórico compartido + log dedicado)
{
  zcat "$LOG_DIR"/access.log.*.gz 2>/dev/null | grep -F "migrationflow.viajeinteligencia.com" || true
  cat "$LOG_DIR"/access.log "$LOG_DIR"/access.log.1 2>/dev/null | grep -F "migrationflow.viajeinteligencia.com" || true
  cat "$DEDICATED" 2>/dev/null || true
} > "$FILTERED"

goaccess -f "$FILTERED" --log-format=COMBINED -o "$OUT" --no-global-config 2>/dev/null || exit 1

chmod 644 "$OUT" "$FILTERED"
