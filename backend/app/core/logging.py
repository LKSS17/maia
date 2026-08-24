"""Configuração de logs estruturados locais."""

import sys
from pathlib import Path
from loguru import logger
from backend.app.core.config import settings

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

logger.remove()

logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

logger.add(
    LOGS_DIR / "maia_{time:YYYY-MM-DD}.log",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    level=settings.LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)
