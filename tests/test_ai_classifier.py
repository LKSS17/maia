"""Testes de classificação via IA com simulação de API e tratamento de erros."""

import pytest
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.entities import (
    Cliente, PlanoContas, Transacao, TipoMovimento, StatusRevisao, OrigemClassificacao
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


def test_ai_batch_classification_success(db_session):
    cliente = Cliente(nome="Cliente IA", documento="20.000.000/0001-20")
    db_session.add(cliente)
    db_session.commit()

    c_combustivel = PlanoContas(
        cliente_id=cliente.id, numero_conta="4.1.5.01", descricao="Combustíveis e Lubrificantes", tipo="Despesa"
    )
    db_session.add(c_combustivel)
    db_session.commit()

    tx = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="POSTO IPIRANGA KM 12",
        valor=Decimal("150.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    # Mock do cliente Gemini
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = f"""{{
        "classificacoes": [
            {{
                "transacao_id": {tx.id},
                "numero_conta": "4.1.5.01",
                "conta_id": {c_combustivel.id},
                "confianca": 0.95,
                "justificativa": "Identificado pagamento em posto de combustível."
            }}
        ]
    }}"""
    mock_genai_client.models.generate_content.return_value = mock_response

    service = GeminiClassifierService(db=db_session, client=mock_genai_client)
    service.classify_batch(cliente.id, [tx])

    assert tx.conta_classificada_id == c_combustivel.id
    assert tx.origem_classificacao == OrigemClassificacao.IA
    assert tx.confianca == Decimal("0.95")
    assert tx.status_revisao == StatusRevisao.CONFIRMADO


def test_ai_classification_degraded_mode_on_failure(db_session):
    cliente = Cliente(nome="Cliente IA Falha", documento="21.000.000/0001-21")
    db_session.add(cliente)
    db_session.commit()

    conta = PlanoContas(cliente_id=cliente.id, numero_conta="4.1.1.01", descricao="Despesas Gerais", tipo="Despesa")
    db_session.add(conta)
    db_session.commit()

    tx = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="COMPRA DESCONHECIDA 123",
        valor=Decimal("50.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    # Simular falha de rede/API externa
    mock_genai_client = MagicMock()
    mock_genai_client.models.generate_content.side_effect = Exception("API Unavailable (Error 503)")

    service = GeminiClassifierService(db=db_session, client=mock_genai_client)
    
    # Não deve lançar exceção nem travar o fluxo
    service.classify_batch(cliente.id, [tx])

    assert tx.conta_classificada_id is None
    assert tx.status_revisao == StatusRevisao.PENDENTE
