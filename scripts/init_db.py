#!/usr/bin/env python3
"""Inicializa el esquema de la base de datos (idempotente)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.db import init_db  # noqa: E402


if __name__ == "__main__":
    init_db()
    print("Esquema MigrationFlow OSINT inicializado.")
