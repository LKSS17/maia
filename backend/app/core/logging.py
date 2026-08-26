"""Configuração centralizada de logs estruturados."""

import sys
from pathlib import Path
from loguru import logger
from platformdirs import user_log_dir


def get_log_dir() -> Path:
    log_path = Path(user_log_dir(appname="MAIA", appauthor="MAIA"))
    try:
        log_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_path = Path.home() / ".maia" / "logs"
        log_path.mkdir(parents=True, exist_ok=True)
    return log_path


LOGS_DIR = get_log_dir()
LOG_FILE = LOGS_DIR / "maia.log"

# Remove sinks padrão
logger.remove()

# Adiciona sink no console apenas se stdout estiver disponível (fora de modo windowed estrito)
if sys.stdout is not None:
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

# Sink persistente em arquivo de log de usuário
try:
    logger.add(
        str(LOG_FILE),
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        encoding="utf-8",
        enqueue=True
    )
except Exception as e:
    # Fallback seguro para evitar crash no import
    pass