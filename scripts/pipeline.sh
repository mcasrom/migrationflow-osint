#!/usr/bin/env bash
# Ejecuta el pipeline de colectores de MigrationFlow OSINT (cron-friendly).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/venv/bin:$PATH"
export PYTHONUNBUFFERED=1
python run.py --init-db >> logs/pipeline.log 2>&1
echo "[pipeline] $(date -Is) OK" >> logs/pipeline.log
