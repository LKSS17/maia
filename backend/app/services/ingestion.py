"""Serviço de Ingestão de Extratos com persistência em lote e deduplicação SHA-256."""

import hashlib
from typing import List, Tuple
from sqlalchemy.orm import Session

from backend.app.models.entities import Extrato, Transacao
from backend.app.repositories.extrato_repository import ExtratoRepository
from backend.app.services.parsers import OFXParser, CSVParser, PDFParser, StatementParseResult


class StatementIngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.extrato_repo = ExtratoRepository(db)

    def compute_sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def ingest_statement(self, cliente_id: int, filename: str, content: bytes) -> Tuple[Extrato, List[Transacao]]:
        file_hash = self.compute_sha256(content)

        existing_extrato = self.extrato_repo.get_by_hash(file_hash)
        if existing_extrato:
            raise ValueError(f"O extrato '{filename}' já foi importado anteriormente (Deduplicação SHA-256 ativa).")

        lower_fn = filename.lower()
        if lower_fn.endswith(".ofx"):
            parse_result: StatementParseResult = OFXParser().parse(content)
        elif lower_fn.endswith(".csv"):
            parse_result = CSVParser().parse(content)
        elif lower_fn.endswith(".pdf"):
            parse_result = PDFParser().parse(content)
        else:
            raise ValueError("Formato não suportado. Utilize arquivos .ofx, .csv ou .pdf.")

        if not parse_result.transacoes:
            raise ValueError("Nenhuma transação válida encontrada no arquivo fornecido.")

        # Cabeçalho do Extrato
        extrato = Extrato(
            cliente_id=cliente_id,
            nome_arquivo=filename,
            hash_sha256=file_hash,
            total_transacoes=len(parse_result.transacoes)
        )
        self.db.add(extrato)
        self.db.flush()

        # Inserção em lote (Batch)
        tx_entities: List[Transacao] = []
        for item in parse_result.transacoes:
            tx = Transacao(
                cliente_id=cliente_id,
                extrato_id=extrato.id,
                data=item.data,
                descricao_banco=item.descricao,
                documento=item.documento,
                valor=item.valor,
                tipo_movimento=item.tipo_movimento
            )
            tx_entities.append(tx)

        self.db.add_all(tx_entities)
        self.db.commit()

        for tx in tx_entities:
            self.db.refresh(tx)

        return extrato, tx_entities