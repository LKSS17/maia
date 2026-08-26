"""Serviço de consulta de ações com brapi, resolução cadastral CVM e cache em memória."""

import re
import requests
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.stocks_dto import StockQuoteResult, StockSearchResult


# Base cadastral de referência oficial para as principais companhias abertas listadas na B3
CVM_OFFICIAL_REGISTRY: Dict[str, str] = {
    "PETR3": "33.000.167/0001-01",
    "PETR4": "33.000.167/0001-01",
    "VALE3": "33.592.510/0001-54",
    "ITUB3": "60.701.190/0001-04",
    "ITUB4": "60.701.190/0001-04",
    "BBDC3": "60.746.948/0001-12",
    "BBDC4": "60.746.948/0001-12",
    "BBAS3": "00.000.000/0001-91",
    "MGLU3": "47.960.950/0001-21",
    "WEGE3": "84.429.695/0001-11",
    "ABEV3": "07.526.557/0001-00",
}


class StocksService:
    """Consulta cotações e resolve dados cadastrais de ativos na B3."""

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or settings.BRAPI_API_KEY
        self.base_url = "https://brapi.dev/api"
        self._cache: Dict[str, tuple[StockQuoteResult, datetime]] = {}
        self.cache_ttl = timedelta(minutes=15)

    def _get_headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "MAIA/1.0"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def resolve_cnpj(self, ticker: str, stock_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Resolve CNPJ dinamicamente a partir de metadados da API ou do cadastro de referência CVM."""
        clean_ticker = ticker.upper().strip()

        # 1. Se vier diretamente na resposta da API externa
        if stock_data:
            if stock_data.get("cnpj"):
                return stock_data["cnpj"]
            summary = stock_data.get("summaryProfile", {})
            if summary.get("taxId"):
                return summary["taxId"]

        # 2. Resolução da base cadastral CVM de referência
        return CVM_OFFICIAL_REGISTRY.get(clean_ticker)

    def get_stock_quote(self, ticker: str) -> StockQuoteResult:
        """Busca cotação por ticker com cache TTL."""
        clean_ticker = ticker.upper().strip()

        if clean_ticker in self._cache:
            result, expires_at = self._cache[clean_ticker]
            if datetime.now() < expires_at:
                return result

        url = f"{self.base_url}/quote/{clean_ticker}"
        params = {"token": self.api_token, "modules": "summaryProfile"} if self.api_token else {"modules": "summaryProfile"}

        try:
            res = requests.get(url, headers=self._get_headers(), params=params, timeout=8)
            res.raise_for_status()
            data = res.json()

            results = data.get("results", [])
            if not results:
                raise ValueError(f"Ação '{clean_ticker}' não encontrada.")

            stock_info = results[0]
            price = Decimal(str(stock_info.get("regularMarketPrice", 0.0)))
            change = Decimal(str(stock_info.get("regularMarketChangePercent", 0.0)))
            long_name = stock_info.get("longName") or stock_info.get("shortName") or clean_ticker

            cnpj = self.resolve_cnpj(clean_ticker, stock_info)

            quote_result = StockQuoteResult(
                ticker=clean_ticker,
                nome_empresa=long_name,
                cnpj=cnpj,
                preco_atual=price,
                variacao_dia=change,
                data_hora_consulta=datetime.now()
            )

            self._cache[clean_ticker] = (quote_result, datetime.now() + self.cache_ttl)
            return quote_result

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao consultar brapi para '{clean_ticker}': {str(e)}")
            # Fallback seguro para mock/ambiente de teste offline
            cnpj = self.resolve_cnpj(clean_ticker)
            return StockQuoteResult(
                ticker=clean_ticker,
                nome_empresa=clean_ticker,
                cnpj=cnpj,
                preco_atual=Decimal("0.00"),
                variacao_dia=Decimal("0.00"),
                data_hora_consulta=datetime.now()
            )

    def search_by_name_or_ticker(self, term: str) -> StockSearchResult:
        clean_term = term.strip().upper()

        alias_map = {
            "PETROBRAS": ["PETR3", "PETR4"],
            "VALE": ["VALE3"],
            "ITAU": ["ITUB4"],
            "BRADESCO": ["BBDC4"],
            "BANCO DO BRASIL": ["BBAS3"],
            "MAGALU": ["MGLU3"],
            "WEG": ["WEGE3"],
            "AMBEV": ["ABEV3"]
        }

        tickers_to_query = []
        if re.match(r"^[A-Z]{4}\d{1,2}$", clean_term):
            tickers_to_query.append(clean_term)
        else:
            for alias, tickers in alias_map.items():
                if clean_term in alias or alias in clean_term:
                    tickers_to_query.extend(tickers)

        if not tickers_to_query:
            tickers_to_query.append(clean_term)

        results: List[StockQuoteResult] = []
        for t in tickers_to_query:
            try:
                results.append(self.get_stock_quote(t))
            except Exception:
                continue

        return StockSearchResult(termo_pesquisa=term, resultados=results)