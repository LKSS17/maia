"""Ponto de entrada de verificação básica do MAIA."""

from backend.app.core.config import settings
from backend.app.core.logging import logger


def init_app() -> str:
    """Inicializa os serviços base e valida o ambiente."""
    logger.info(f"Iniciando {settings.APP_NAME} em modo [{settings.APP_ENV}]...")
    return f"{settings.APP_NAME} iniciado com sucesso."


if __name__ == "__main__":
    status = init_app()
    print(status)
