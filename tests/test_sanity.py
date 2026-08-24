"""Testes de sanidade e inicialização do MAIA."""

from backend.app.core.config import settings
from backend.main import init_app


def test_app_name():
    """Valida se a identidade do produto está configurada corretamente."""
    assert settings.APP_NAME == "MAIA"


def test_init_app():
    """Valida a execução de inicialização padrão."""
    result = init_app()
    assert "MAIA" in result
    assert "sucesso" in result
