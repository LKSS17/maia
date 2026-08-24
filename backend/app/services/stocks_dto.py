"""Esquemas de dados para cotações e cruzamento de ações e CNPJ."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel


class StockQuoteResult(BaseModel):
    """Resultado estruturado de cotação e dados cadastrais da ação."""
    ticker: str
    nome_empresa: str
    cnpj: Optional[str] = None
    preco_atual: Decimal
    variacao_dia: Optional[Decimal] = None
    data_hora_consulta: datetime
    fonte_cotacao: str = "brapi.dev"
    fonte_cnpj: str = "CVM"


class StockSearchResult(BaseModel):
    """Lista de correspondências encontradas ao buscar por nome."""
    termo_pesquisa: str
    resultados: List[StockQuoteResult]
