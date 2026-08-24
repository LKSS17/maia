"""Esquema de dados para inferência contábil via LLM."""

from typing import List, Optional
from decimal import Decimal
from pydantic import BaseModel, Field


class AIClassificationItem(BaseModel):
    """Classificação sugerida pela IA para uma transação individual."""
    transacao_id: int
    numero_conta: str
    conta_id: int
    confianca: Decimal = Field(..., ge=Decimal("0.0"), le=Decimal("1.0"))
    justificativa: str


class AIBatchResponse(BaseModel):
    """Lote de classificações retornado pela IA."""
    classificacoes: List[AIClassificationItem]
