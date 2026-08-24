"""Testes de banco de dados e repositórios usando SQLite in-memory."""

import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.db.session import Base
from backend.app.models.entities import (
    Cliente, PlanoContas, Transacao, TipoMovimento, StatusRevisao, OrigemClassificacao, ExtratoImportado
)
from backend.app.repositories.client_repository import ClientRepository
from backend.app.repositories.transaction_repository import TransactionRepository
from backend.app.repositories.statement_repository import StatementRepository


@pytest.fixture
def db_session():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_create_and_query_client(db_session):
    repo = ClientRepository(db_session)
    cliente = Cliente(nome="Cliente Teste", documento="00.000.000/0001-00")
    created = repo.create(cliente)

    assert created.id is not None
    fetched = repo.get_by_document("00.000.000/0001-00")
    assert fetched is not None
    assert fetched.nome == "Cliente Teste"


def test_transaction_cascade_and_query(db_session):
    client_repo = ClientRepository(db_session)
    tx_repo = TransactionRepository(db_session)

    cliente = client_repo.create(Cliente(nome="Cliente Alpha", documento="11.111.111/0001-11"))
    
    t1 = Transacao(
        cliente_id=cliente.id,
        data=datetime.utcnow(),
        descricao_banco="PIX ENVIADO",
        valor=Decimal("150.00"),
        tipo_movimento=TipoMovimento.SAIDA,
        status_revisao=StatusRevisao.PENDENTE
    )
    tx_repo.create(t1)

    pendentes = tx_repo.list_by_client(cliente.id, status=StatusRevisao.PENDENTE)
    assert len(pendentes) == 1
    assert pendentes[0].descricao_banco == "PIX ENVIADO"


def test_statement_deduplication(db_session):
    client_repo = ClientRepository(db_session)
    stmt_repo = StatementRepository(db_session)

    cliente = client_repo.create(Cliente(nome="Cliente Beta", documento="22.222.222/0001-22"))
    
    stmt = ExtratoImportado(
        cliente_id=cliente.id,
        nome_arquivo="extrato_junho.ofx",
        hash_arquivo="abc123hash"
    )
    stmt_repo.create(stmt)

    assert stmt_repo.exists_hash(cliente.id, "abc123hash") is True
    assert stmt_repo.exists_hash(cliente.id, "hash_inexistente") is False
