from sqlalchemy.orm import Session
from backend.app.models.entities import LogAuditoria


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def log_action(self, transacao_id: int, acao: str, detalhes: str = "", usuario: str = "sistema") -> LogAuditoria:
        log = LogAuditoria(
            transacao_id=transacao_id,
            acao=acao,
            detalhes=detalhes,
            usuario=usuario
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
