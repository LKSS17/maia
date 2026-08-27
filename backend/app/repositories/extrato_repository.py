from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.entities import Extrato


class ExtratoRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_hash(self, hash_sha256: str) -> Optional[Extrato]:
        return self.db.query(Extrato).filter(Extrato.hash_sha256 == hash_sha256).first()

    def create(self, extrato: Extrato) -> Extrato:
        self.db.add(extrato)
        self.db.commit()
        self.db.refresh(extrato)
        return extrato
