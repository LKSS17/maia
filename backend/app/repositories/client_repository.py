"""Repositório de acesso a dados para Clientes."""

from typing import Optional, List
from sqlalchemy.orm import Session
from backend.app.models.entities import Cliente
from backend.app.repositories.base import BaseRepository


class ClientRepository(BaseRepository[Cliente]):
    def __init__(self, db: Session):
        super().__init__(Cliente, db)

    def get_by_document(self, document: str) -> Optional[Cliente]:
        return self.db.query(Cliente).filter(Cliente.documento == document).first()
