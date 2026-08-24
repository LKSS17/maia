"""Esquemas de dados para o módulo de revisão humana."""

from datetime import date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel
from backend.app.models.entities import TipoMovimento, StatusRevisao, OrigemClassificacao


class ReviewItemDTO(BaseModel):
    """Representação de uma transação para a tela de revisão."""
    id: int
    data: date
    descricao_banco: str
    valor: Decimal
    tipo_movimento: TipoMovimento
    conta_id: Optional[int] = None
    numero_conta: Optional[str] = None
    descricao_conta: Optional[str] = None
    origem: Optional[OrigemClassificacao] = None
    confianca: Decimal
    nivel_confianca: str  # 'ALTA', 'MEDIA', 'BAIXA'
    status_revisao: StatusRevisao


class ManualCorrectionRequest(BaseModel):
    """Payload para correção manual de uma transação."""
    transacao_id: int
    nova_conta_id: int
    salvar_como_regra: bool = True
    criterio_texto: Optional[str] = None
    usuario: str = "usuaria"
