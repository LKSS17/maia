from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.models.entities import RegraClassificacao


class RegraRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_client(self, cliente_id: int) -> List[RegraClassificacao]:
        return self.db.query(RegraClassificacao).filter(
            RegraClassificacao.cliente_id == cliente_id,
            RegraClassificacao.ativo == True
        ).all()

    def create(self, regra: RegraClassificacao) -> RegraClassificacao:
        self.db.add(regra)
        self.db.commit()
        self.db.refresh(regra)
        return regra
