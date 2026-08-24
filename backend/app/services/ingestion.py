"""Serviço de Ingestão de Extratos com deduplicação via hash SHA-256."""

import hashlib
from typing import Tuple, List
from sqlalchemy.orm import Session

from backend.app.models.entities import ExtratoImportado, Transacao, StatusRevisao
from backend.app.repositories.statement_repository import StatementRepository
from backend.app.repositories.transaction_repository import TransactionRepository
from backend.app.services.statement_dto import StatementBatch
from backend.app.services.parsers import OfxParser, CsvParser, PdfParser, BaseParser


class StatementIngestionService:
    """Orquestra leitura, hash, deduplicação e persistência inicial de transações."""

    def __init__(self, db: Session):
        self.db = db
        self.statement_repo = StatementRepository(db)
        self.transaction_repo = TransactionRepository(db)
        self.parsers = {
            "ofx": OfxParser(),
            "csv": CsvParser(),
            "pdf": PdfParser()
        }

    def compute_file_hash(self, file_content: bytes) -> str:
        """Gera hash SHA-256 seguro para garantir idempotência da importação."""
        return hashlib.sha256(file_content).hexdigest()

    def get_parser_for_filename(self, filename: str) -> BaseParser:
        ext = filename.lower().split(".")[-1]
        if ext not in self.parsers:
            raise ValueError(f"Extensão de arquivo '.{ext}' não é suportada. Use OFX, CSV ou PDF.")
        return self.parsers[ext]

    def ingest_statement(
        self, cliente_id: int, filename: str, content_bytes: bytes
    ) -> Tuple[ExtratoImportado, List[Transacao]]:
        """Processa arquivo, valida duplicatas e salva transações com status PENDENTE."""
        file_hash = self.compute_file_hash(content_bytes)

        if self.statement_repo.exists_hash(cliente_id, file_hash):
            raise ValueError(f"O extrato '{filename}' já foi importado anteriormente para este cliente.")

        parser = self.get_parser_for_filename(filename)
        parsed_items = parser.parse(content_bytes, filename)

        if not parsed_items:
            raise ValueError(f"Nenhuma transação válida foi encontrada no arquivo '{filename}'.")

        # 1. Registrar extrato importado
        extrato = ExtratoImportado(
            cliente_id=cliente_id,
            nome_arquivo=filename,
            hash_arquivo=file_hash
        )
        self.statement_repo.create(extrato)

        # 2. Persistir transações no banco
        persisted_transactions: List[Transacao] = []
        for item in parsed_items:
            tx = Transacao(
                cliente_id=cliente_id,
                data=item.data,
                descricao_banco=item.descricao,
                valor=item.valor,
                tipo_movimento=item.tipo_movimento,
                confianca=item.confianca_extracao,
                status_revisao=StatusRevisao.PENDENTE
            )
            self.transaction_repo.create(tx)
            persisted_transactions.append(tx)

        return extrato, persisted_transactions
