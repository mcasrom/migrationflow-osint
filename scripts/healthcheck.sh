#!/usr/bin/env bash
# healthcheck.sh — MigrationFlow OSINT: comprueba la API y la relanza si no responde.
# Uso en cron: */5 * * * * cd /home/deploy/migrationflow-osint && ./scripts/healthcheck.sh >> logs/healthcheck.log 2>&1
set -u

HEALTH_URL="http://127.0.0.1:8600/health"
CURL_TIMEOUT=10
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDIR="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR/..")"
STATE_FILE="$CDIR/logs/healthcheck.state"
mkdir -p "$CDIR/logs"

prev_state=$(cat "$STATE_FILE" 2>/dev/null || echo "up")

is_ok() {
    [ -n "$1" ] && echo "$1" | grep -q '"status":"ok"'
}

HEALTH=$(curl -s --max-time $CURL_TIMEOUT "$HEALTH_URL" 2>/dev/null || echo "")
if is_ok "$HEALTH"; then
    echo "[$(date -u +%FT%TZ)] [OK] api responde"
    echo "up" > "$STATE_FILE"
    exit 0
fi

echo "[$(date -u +%FT%TZ)] [DOWN] api no responde — relanzando"
if ! pm2 jlist 2>/dev/null | grep -q '"name":"migrationflow-api"'; then
    pm2 resurrect >/dev/null 2>&1 || true
    sleep 2
fi
pm2 restart migrationflow-api --update-env >/dev/null 2>&1 || \
    (cd "$CDIR" && pm2 start server.py --name migrationflow-api --interpreter ./venv/bin/python >/dev/null 2>&1)
sleep 6

HEALTH=$(curl -s --max-time $CURL_TIMEOUT "$HEALTH_URL" 2>/dev/null || echo "")
if is_ok "$HEALTH"; then
    echo "[$(date -u +%FT%TZ)] [RECOVERED] api relanzada"
    echo "up" > "$STATE_FILE"
    exit 0
fi
echo "[$(date -u +%FT%TZ)] [STILL DOWN] api no responde tras relanzar"
echo "down" > "$STATE_FILE"
exit 1
