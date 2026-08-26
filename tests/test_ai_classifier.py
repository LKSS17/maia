"""Testes para o serviço de classificação via IA Gemini com cache desacoplado de sessão."""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.entities import (
    Cliente, PlanoContas, Transacao, TipoMovimento, OrigemClassificacao
)
from backend.app.services.ai_classifier import GeminiClassifierService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_gemini_classify_batch_with_cache(db_session):
    cliente = Cliente(nome="Cliente Teste IA", documento="12.345.678/0001-90")
    db_session.add(cliente)
    db_session.commit()

    conta = PlanoContas(
        cliente=cliente,
        numero_conta="4.1.2.01",
        descricao="Serviços de Terceiros",
        tipo="Despesa"
    )
    db_session.add(conta)
    db_session.commit()

    tx = Transacao(
        cliente=cliente,
        data=datetime.now(),
        descricao_banco="PAGTO FORNECEDOR AWS",
        valor=Decimal("450.00"),
        tipo_movimento=TipoMovimento.SAIDA
    )
    db_session.add(tx)
    db_session.commit()

    # Instância sem DB acoplado no construtor
    service = GeminiClassifierService()

    # Simula entrada em cache de longa duração
    norm_key = service._normalize_key("PAGTO FORNECEDOR AWS")
    service._local_cache[norm_key] = {
        "conta_id": conta.id,
        "confianca": 0.95
    }

    # Passa o db_session explicitamente como primeiro parâmetro
    result = service.classify_batch(db_session, cliente.id, [tx])

    assert len(result) == 1
    assert result[0].conta_classificada_id == conta.id
    assert result[0].confianca == Decimal("0.95")
    assert result[0].origem_classificacao == OrigemClassificacao.IA