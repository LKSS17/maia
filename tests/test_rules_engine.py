"""Testes para o motor de regras com execução em lote e cache de regras."""

import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.entities import (
    Cliente, PlanoContas, RegraClassificacao, Transacao,
    TipoMovimento, StatusRevisao, OrigemClassificacao, CriterioRegra
)
from backend.app.services.rules_engine import RulesEngineService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_classify_batch_with_rules(db_session):
    cliente = Cliente(nome="Cliente Teste Batch", documento="11.222.333/0001-44")
    db_session.add(cliente)
    db_session.commit()

    conta1 = PlanoContas(cliente=cliente, numero_conta="3.1.1.01", descricao="Receitas de Vendas", tipo="Receita")
    conta2 = PlanoContas(cliente=cliente, numero_conta="4.1.2.01", descricao="Despesas Bancarias", tipo="Despesa")
    db_session.add_all([conta1, conta2])
    db_session.commit()

    regra = RegraClassificacao(
        cliente=cliente,
        criterio=CriterioRegra.CONFORME,
        padrao="PAGAMENTO CLIENTE XPTO",
        conta_destino=conta1
    )
    db_session.add(regra)
    db_session.commit()

    tx1 = Transacao(cliente=cliente, data=datetime.now(), descricao_banco="PAGAMENTO CLIENTE XPTO LTDA", valor=Decimal("1500.00"), tipo_movimento=TipoMovimento.ENTRADA)
    tx2 = Transacao(cliente=cliente, data=datetime.now(), descricao_banco="TARIFA MENSAL BANCARIA", valor=Decimal("45.00"), tipo_movimento=TipoMovimento.SAIDA)
    tx3 = Transacao(cliente=cliente, data=datetime.now(), descricao_banco="OUTRO LANCAMENTO SEM REGRA", valor=Decimal("100.00"), tipo_movimento=TipoMovimento.SAIDA)
    db_session.add_all([tx1, tx2, tx3])
    db_session.commit()

    service = RulesEngineService(db_session)
    result = service.classify_batch(cliente.id, [tx1, tx2, tx3])

    assert len(result) == 3
    # Tx 1: Regra padrão
    assert tx1.conta_classificada_id == conta1.id
    assert tx1.status_revisao == StatusRevisao.CONFIRMADO

    # Tx 2: Regra semântica global de despesa bancária
    assert tx2.conta_classificada_id == conta2.id
    assert tx2.status_revisao == StatusRevisao.CONFIRMADO

    # Tx 3: Sem classificação
    assert tx3.conta_classificada_id is None
    assert tx3.status_revisao == StatusRevisao.PENDENTE