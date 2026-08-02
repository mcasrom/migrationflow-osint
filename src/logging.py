import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def _make_handler() -> RotatingFileHandler:
    handler = RotatingFileHandler(
        LOG_DIR / "migrationflow.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    return handler


def get_logger(name: str = "mf") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.addHandler(_make_handler())
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(console)
    logger.propagate = False
    return logger
