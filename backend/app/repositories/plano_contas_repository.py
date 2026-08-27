from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.models.entities import PlanoContas


class PlanoContasRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_cliente(self, cliente_id: int) -> List[PlanoContas]:
        return self.db.query(PlanoContas).filter(PlanoContas.cliente_id == cliente_id).all()

    def get_by_id(self, conta_id: int) -> Optional[PlanoContas]:
        return self.db.query(PlanoContas).filter(PlanoContas.id == conta_id).first()
