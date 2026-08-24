"""Repositório de acesso a dados para Transações."""

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.models.entities import Transacao, StatusRevisao
from backend.app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transacao]):
    def __init__(self, db: Session):
        super().__init__(Transacao, db)

    def list_by_client(self, cliente_id: int, status: Optional[StatusRevisao] = None) -> List[Transacao]:
        query = self.db.query(Transacao).filter(Transacao.cliente_id == cliente_id)
        if status:
            query = query.filter(Transacao.status_revisao == status)
        return query.all()
