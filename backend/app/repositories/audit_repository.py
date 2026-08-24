"""Repositório para persistência de logs de auditoria."""

from typing import List
from datetime import datetime
from sqlalchemy.orm import Session

from backend.app.models.entities import LogAuditoria
from backend.app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[LogAuditoria]):
    def __init__(self, db: Session):
        super().__init__(LogAuditoria, db)

    def log_action(self, transacao_id: int, acao: str, usuario: str = "usuaria", detalhes: str = None) -> LogAuditoria:
        """Registra uma ação de auditoria imutável."""
        log = LogAuditoria(
            transacao_id=transacao_id,
            acao=acao,
            usuario=usuario,
            detalhes=detalhes,
            timestamp=datetime.utcnow()
        )
        return self.create(log)

    def list_by_transaction(self, transacao_id: int) -> List[LogAuditoria]:
        return self.db.query(LogAuditoria).filter(LogAuditoria.transacao_id == transacao_id).all()
