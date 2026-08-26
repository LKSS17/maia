"""Data Transfer Objects para interação estruturada com o classificador Gemini."""

from typing import List, Optional
from pydantic import BaseModel, Field


class AIClassificationItem(BaseModel):
    index: int = Field(..., description="Índice da transação correspondente no lote")
    conta_id: Optional[int] = Field(None, description="ID da conta contábil correspondente")
    confianca: float = Field(..., description="Nível de confiança entre 0.0 e 1.0")
    justificativa: str = Field(..., description="Justificativa contábil para a classificação")


class AIBatchResponse(BaseModel):
    classificacoes: List[AIClassificationItem] = Field(
        default_factory=list,
        description="Lista de classificações geradas para o lote"
    )