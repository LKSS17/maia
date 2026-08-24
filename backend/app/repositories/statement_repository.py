"""Repositório de Extratos e deduplicação."""

from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.entities import ExtratoImportado
from backend.app.repositories.base import BaseRepository


class StatementRepository(BaseRepository[ExtratoImportado]):
    def __init__(self, db: Session):
        super().__init__(ExtratoImportado, db)

    def exists_hash(self, cliente_id: int, hash_arquivo: str) -> bool:
        return self.db.query(ExtratoImportado).filter(
            ExtratoImportado.cliente_id == cliente_id,
            ExtratoImportado.hash_arquivo == hash_arquivo
        ).first() is not None
