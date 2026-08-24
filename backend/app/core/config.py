"""Módulo de configuração centralizada do sistema MAIA."""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas de variáveis de ambiente."""

    APP_NAME: str = "MAIA"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "sqlite:///./maia.db"
    
    GEMINI_API_KEY: str | None = None
    BRAPI_API_KEY: str | None = None
    ENCRYPTION_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
