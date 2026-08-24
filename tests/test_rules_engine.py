"""Testes do motor de classificação por regras (Camadas 1 e 2) e auto-aprendizado."""

import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.entities import (
    Cliente, PlanoContas, Transacao, RegraClassificacao,
    TipoMovimento, StatusRevisao, CriterioRegra, OrigemClassificacao
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


def test_layer_1_exact_match(db_session):
    cliente = Cliente(nome="Cliente Regras", documento="12.000.000/0001-01")
    db_session.add(cliente)
    db_session.commit()

    conta = PlanoContas(cliente_id=cliente.id, numero_conta="4.1.1", descricao="Telefonia e Internet", tipo="Despesa")
    db_session.add(conta)
    db_session.commit()

    regra = RegraClassificacao(
        cliente_id=cliente.id,
        criterio=CriterioRegra.TEXTO,
        valor_criterio="VIVO FIBRA",
        conta_id=conta.id
    )
    db_session.add(regra)
    db_session.commit()

    tx = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="DEB AUT VIVO FIBRA SP",
        valor=Decimal("120.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    engine_svc = RulesEngineService(db_session)
    classified_tx = engine_svc.classify_transaction(tx)

    assert classified_tx.conta_classificada_id == conta.id
    assert classified_tx.origem_classificacao == OrigemClassificacao.REGRA_EXATA
    assert classified_tx.status_revisao == StatusRevisao.CONFIRMADO


def test_layer_2_accounting_keyword_match(db_session):
    cliente = Cliente(nome="Cliente Contabil", documento="13.000.000/0001-02")
    db_session.add(cliente)
    db_session.commit()

    conta_tarifa = PlanoContas(cliente_id=cliente.id, numero_conta="4.2.1", descricao="Tarifas Bancárias", tipo="Despesa")
    db_session.add(conta_tarifa)
    db_session.commit()

    tx = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="TAR COBRANCA MENSAL",
        valor=Decimal("45.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    engine_svc = RulesEngineService(db_session)
    classified_tx = engine_svc.classify_transaction(tx)

    assert classified_tx.conta_classificada_id == conta_tarifa.id
    assert classified_tx.origem_classificacao == OrigemClassificacao.REGRA_CONTABIL
    assert classified_tx.status_revisao == StatusRevisao.CONFIRMADO


def test_unmatched_transaction_stays_pending(db_session):
    cliente = Cliente(nome="Cliente Sem Match", documento="14.000.000/0001-03")
    db_session.add(cliente)
    db_session.commit()

    tx = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="PAGAMENTO DESCONHECIDO XYZ 999",
        valor=Decimal("300.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    engine_svc = RulesEngineService(db_session)
    classified_tx = engine_svc.classify_transaction(tx)

    assert classified_tx.conta_classificada_id is None
    assert classified_tx.origem_classificacao is None
    assert classified_tx.status_revisao == StatusRevisao.PENDENTE


def test_learning_by_correction(db_session):
    cliente = Cliente(nome="Cliente Aprendiz", documento="15.000.000/0001-04")
    db_session.add(cliente)
    db_session.commit()

    conta = PlanoContas(cliente_id=cliente.id, numero_conta="4.3.1", descricao="Limpeza e Conservacao", tipo="Despesa")
    db_session.add(conta)
    db_session.commit()

    tx1 = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="PRODUTOS LIMPEZA SILVA",
        valor=Decimal("80.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx1)
    db_session.commit()

    engine_svc = RulesEngineService(db_session)
    # Usuária revisa manualmente e o sistema aprende a regra
    engine_svc.confirm_and_learn_rule(tx1.id, conta.id, criterio_texto="LIMPEZA SILVA")

    # Segunda transação similar que chega depois
    tx2 = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="NF 123 LIMPEZA SILVA LTDA",
        valor=Decimal("95.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx2)
    db_session.commit()

    # O motor agora deve classificar automaticamente pela regra aprendida
    classified_tx2 = engine_svc.classify_transaction(tx2)
    assert classified_tx2.conta_classificada_id == conta.id
    assert classified_tx2.origem_classificacao == OrigemClassificacao.REGRA_EXATA
