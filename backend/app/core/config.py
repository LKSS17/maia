"""Configurações globais da aplicação MAIA com caminhos resilientes."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from platformdirs import user_data_dir, user_log_dir


def get_app_data_dir() -> Path:
    """Garante e retorna o diretório de dados do usuário."""
    path = Path(user_data_dir(appname="MAIA", appauthor="MAIA"))
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        path = Path.home() / ".maia"
        path.mkdir(parents=True, exist_ok=True)
    return path


APP_DATA_DIR = get_app_data_dir()
DEFAULT_DB_PATH = APP_DATA_DIR / "maia.db"


class Settings(BaseSettings):
    APP_NAME: str = "MAIA"
    PROJECT_NAME: str = "MAIA"
    APP_ENV: str = "production"
    ENVIRONMENT: str = "production"
    
    # Armazenamento SQLite fora da pasta de instalação binária
    DATABASE_URL: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    
    GEMINI_API_KEY: str = ""
    BRAPI_API_KEY: str = ""
    ENCRYPTION_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()