"""Repositório de regras de classificação configuradas."""

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.models.entities import RegraClassificacao, CriterioRegra
from backend.app.repositories.base import BaseRepository


class RuleRepository(BaseRepository[RegraClassificacao]):
    def __init__(self, db: Session):
        super().__init__(RegraClassificacao, db)

    def list_by_client(self, cliente_id: int) -> List[RegraClassificacao]:
        return self.db.query(RegraClassificacao).filter(RegraClassificacao.cliente_id == cliente_id).all()

    def find_matching_rule(self, cliente_id: int, text: str) -> Optional[RegraClassificacao]:
        """Busca se algum critério de texto ou CNPJ cadastrado está presente na descrição."""
        rules = self.list_by_client(cliente_id)
        text_upper = text.upper()
        for rule in rules:
            if rule.valor_criterio.upper() in text_upper:
                return rule
        return None
