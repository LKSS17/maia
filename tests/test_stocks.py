"""Testes unitários para o módulo de cotação e consulta de ações."""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from backend.app.services.stocks_service import StocksService


def test_stocks_quote_with_cache():
    service = StocksService()

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "symbol": "PETR4",
                "shortName": "PETROBRAS PN",
                "longName": "Petróleo Brasileiro S.A. - Petrobras",
                "regularMarketPrice": 38.50,
                "regularMarketChangePercent": 1.25
            }
        ]
    }
    mock_response.status_code = 200

    with patch("requests.get", return_value=mock_response) as mock_get:
        # Primeira chamada: faz requisição externa
        quote1 = service.get_stock_quote("PETR4")
        assert quote1.ticker == "PETR4"
        assert quote1.preco_atual == Decimal("38.5")
        assert quote1.cnpj == "33.000.167/0001-01"
        assert mock_get.call_count == 1

        # Segunda chamada imediata: deve vir do cache (sem chamar requests.get novamente)
        quote2 = service.get_stock_quote("PETR4")
        assert quote2.ticker == "PETR4"
        assert mock_get.call_count == 1


def test_search_by_name_resolution():
    service = StocksService()

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "symbol": "VALE3",
                "longName": "Vale S.A.",
                "regularMarketPrice": 62.10,
                "regularMarketChangePercent": -0.50
            }
        ]
    }
    mock_response.status_code = 200

    with patch("requests.get", return_value=mock_response):
        search_res = service.search_by_name_or_ticker("VALE")
        assert len(search_res.resultados) >= 1
        assert search_res.resultados[0].ticker == "VALE3"
        assert search_res.resultados[0].cnpj == "33.592.510/0001-54"
