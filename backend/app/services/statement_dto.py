"""Data Transfer Objects (DTO) padronizados para transações extraídas de extratos."""

from datetime import date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field
from backend.app.models.entities import TipoMovimento


class ParsedTransaction(BaseModel):
    """Representação normalizada de uma linha de extrato bancário."""
    data: date
    descricao: str = Field(..., min_length=1)
    valor: Decimal = Field(..., decimal_places=2)
    tipo_movimento: TipoMovimento
    fitid: Optional[str] = None
    confianca_extracao: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0.00"), le=Decimal("1.00"))
    aviso_extracao: Optional[str] = None


class StatementBatch(BaseModel):
    """Lote de transações extraídas de um arquivo de extrato."""
    nome_arquivo: str
    hash_arquivo: str
    transacoes: List[ParsedTransaction]
