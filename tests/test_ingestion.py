"""Bateria de testes unitários para os Parsers (OFX, CSV, PDF) e Serviço de Ingestão."""

import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.entities import Cliente, TipoMovimento
from backend.app.repositories.client_repository import ClientRepository
from backend.app.services.parsers import OfxParser, CsvParser
from backend.app.services.ingestion import StatementIngestionService


@pytest.fixture
def db_session():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(bind=test_engine)
    session = TestingSession()
    yield session
    session.close()


def test_csv_parser_semicolon_format():
    csv_content = b"Data;Descricao;Valor\n15/05/2026;PAGAMENTO FORNECEDOR;-1250,50\n16/05/2026;RECEBIMENTO CLIENTE;3400,00\n"
    parser = CsvParser()
    txs = parser.parse(csv_content, "extrato.csv")

    assert len(txs) == 2
    assert txs[0].data == date(2026, 5, 15)
    assert txs[0].descricao == "PAGAMENTO FORNECEDOR"
    assert txs[0].valor == Decimal("1250.50")
    assert txs[0].tipo_movimento == TipoMovimento.SAIDA

    assert txs[1].data == date(2026, 5, 16)
    assert txs[1].valor == Decimal("3400.00")
    assert txs[1].tipo_movimento == TipoMovimento.ENTRADA


def test_ofx_parser_structure():
    ofx_content = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFORMAT:NONE
NEWFILEUID:NONE

<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<CURDEF>BRL
<BANKTRANLIST>
<DTSTART>20260501
<DTEND>20260531
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260510120000
<TRNAMT>-89.90
<FITID>TX00129381
<MEMO>SUPERMERCADO CENTRAL
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""
    parser = OfxParser()
    txs = parser.parse(ofx_content, "extrato.ofx")

    assert len(txs) == 1
    assert txs[0].descricao == "SUPERMERCADO CENTRAL"
    assert txs[0].valor == Decimal("89.90")
    assert txs[0].tipo_movimento == TipoMovimento.SAIDA
    assert txs[0].fitid == "TX00129381"


def test_ingestion_service_deduplication(db_session):
    client_repo = ClientRepository(db_session)
    cliente = client_repo.create(Cliente(nome="Cliente Teste Deduplicacao", documento="99.999.999/0001-99"))

    service = StatementIngestionService(db_session)
    csv_bytes = b"Data;Descricao;Valor\n01/06/2026;TESTE DEPOSITO;500,00\n"

    # Primeira importação: sucesso
    extrato, txs = service.ingest_statement(cliente.id, "extrato_junho.csv", csv_bytes)
    assert len(txs) == 1
    assert extrato.hash_arquivo is not None

    # Segunda importação com o mesmo arquivo: deve bloquear
    with pytest.raises(ValueError, match="já foi importado"):
        service.ingest_statement(cliente.id, "extrato_junho.csv", csv_bytes)
