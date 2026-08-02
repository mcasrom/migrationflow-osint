#!/usr/bin/env bash
# Despliegue de MigrationFlow OSINT en el VPS (PM2 nativo).
set -euo pipefail
cd "$(dirname "$0")"

# 1. Dependencias
./venv/bin/pip install -q -r requirements.txt

# 2. Esquema de BD
./venv/bin/python scripts/init_db.py

# 3. API
pm2 delete migrationflow-api 2>/dev/null || true
pm2 start server.py --name migrationflow-api --interpreter ./venv/bin/python -- --host 0.0.0.0 --port 8600
pm2 save

echo "MigrationFlow OSINT desplegado. API en :8600"
