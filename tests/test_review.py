"""Testes de fluxo de revisão humana e auditoria."""

import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.entities import (
    Cliente, PlanoContas, Transacao, TipoMovimento, StatusRevisao, OrigemClassificacao
)
from backend.app.services.review_service import ReviewService
from backend.app.services.review_dto import ManualCorrectionRequest
from backend.app.repositories.audit_repository import AuditRepository
from backend.app.repositories.rule_repository import RuleRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_list_pending_items_and_confidence(db_session):
    cliente = Cliente(nome="Cliente Revisao", documento="40.000.000/0001-40")
    db_session.add(cliente)
    db_session.commit()

    conta = PlanoContas(cliente=cliente, numero_conta="4.1.2", descricao="Material de Escritorio", tipo="Despesa")
    db_session.add(conta)
    db_session.commit()

    # Transação com confiança média
    tx = Transacao(
        cliente=cliente,
        data=datetime.now(),
        descricao_banco="KALUNGA COMERCIO",
        valor=Decimal("190.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        conta_classificada=conta,
        origem_classificacao=OrigemClassificacao.IA,
        confianca=Decimal("0.75"),
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    service = ReviewService(db_session)
    pendentes = service.get_pending_review_items(cliente.id)

    assert len(pendentes) == 1
    assert pendentes[0].nivel_confianca == "MEDIA"
    assert pendentes[0].descricao_banco == "KALUNGA COMERCIO"


def test_approve_transaction(db_session):
    cliente = Cliente(nome="Cliente Aprovacao", documento="41.000.000/0001-41")
    conta = PlanoContas(cliente=cliente, numero_conta="4.1.3", descricao="Honorarios", tipo="Despesa")
    db_session.add_all([cliente, conta])
    db_session.commit()

    tx = Transacao(
        cliente=cliente,
        data=datetime.now(),
        descricao_banco="HONORARIOS CONTABEIS",
        valor=Decimal("600.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        conta_classificada=conta,
        origem_classificacao=OrigemClassificacao.IA,
        confianca=Decimal("0.80"),
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    service = ReviewService(db_session)
    service.approve_transaction(tx.id, usuario="contadora")

    assert tx.status_revisao == StatusRevisao.CONFIRMADO

    # Verificar registro de auditoria
    audit_repo = AuditRepository(db_session)
    logs = audit_repo.list_by_transaction(tx.id)
    assert len(logs) == 1
    assert logs[0].acao == "APROVACAO"
    assert logs[0].usuario == "contadora"


def test_manual_correction_and_rule_learning(db_session):
    cliente = Cliente(nome="Cliente Correcao", documento="42.000.000/0001-42")
    c_errada = PlanoContas(cliente=cliente, numero_conta="4.1.1", descricao="Despesa Geral", tipo="Despesa")
    c_certa = PlanoContas(cliente=cliente, numero_conta="4.1.9", descricao="Seguros", tipo="Despesa")
    db_session.add_all([cliente, c_errada, c_certa])
    db_session.commit()

    tx = Transacao(
        cliente=cliente,
        data=datetime.now(),
        descricao_banco="PORTO SEGURO CIA",
        valor=Decimal("350.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        conta_classificada=c_errada,
        status_revisao=StatusRevisao.PENDENTE
    )
    db_session.add(tx)
    db_session.commit()

    service = ReviewService(db_session)
    req = ManualCorrectionRequest(
        transacao_id=tx.id,
        nova_conta_id=c_certa.id,
        salvar_como_regra=True,
        criterio_texto="PORTO SEGURO"
    )
    service.correct_manually(req)

    assert tx.conta_classificada_id == c_certa.id
    assert tx.status_revisao == StatusRevisao.REVISADO

    # Validar que a nova regra foi aprendida no banco
    rule_repo = RuleRepository(db_session)
    matching_rule = rule_repo.find_matching_rule(cliente.id, "DEBITO PORTO SEGURO AUTO")
    assert matching_rule is not None
    assert matching_rule.conta_id == c_certa.id
