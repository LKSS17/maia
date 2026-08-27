"""Parsers para extratos bancários nos formatos OFX, CSV e PDF."""

import io
import csv
import re
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel

from backend.app.models.entities import TipoMovimento


class ParsedTransactionItem(BaseModel):
    data: datetime
    descricao: str
    documento: Optional[str] = None
    valor: Decimal
    tipo_movimento: TipoMovimento


class StatementParseResult(BaseModel):
    transacoes: List[ParsedTransactionItem] = []


class BaseParser(ABC):
    @abstractmethod
    def parse(self, content: bytes) -> StatementParseResult:
        pass


class OFXParser(BaseParser):
    def parse(self, content: bytes) -> StatementParseResult:
        import ofxparse
        ofx = ofxparse.OfxParser.parse(io.BytesIO(content))
        items: List[ParsedTransactionItem] = []

        if hasattr(ofx, "account") and hasattr(ofx.account, "statement"):
            for tx in ofx.account.statement.transactions:
                amount = Decimal(str(tx.amount))
                tipo = TipoMovimento.ENTRADA if amount >= 0 else TipoMovimento.SAIDA
                items.append(
                    ParsedTransactionItem(
                        data=tx.date,
                        descricao=tx.memo or tx.payee or "Transação sem descrição",
                        documento=getattr(tx, "checknum", None) or getattr(tx, "id", None),
                        valor=abs(amount),
                        tipo_movimento=tipo
                    )
                )
        return StatementParseResult(transacoes=items)


class CSVParser(BaseParser):
    def parse(self, content: bytes) -> StatementParseResult:
        text = content.decode("utf-8-sig", errors="replace")
        delimiter = ";" if ";" in text.splitlines()[0] else ","
        reader = csv.DictReader(text.splitlines(), delimiter=delimiter)

        items: List[ParsedTransactionItem] = []
        for row in reader:
            normalized_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}

            # Localizar data
            date_str = (
                normalized_row.get("data")
                or normalized_row.get("date")
                or normalized_row.get("dt")
            )
            if not date_str:
                continue

            # Localizar valor
            val_str = (
                normalized_row.get("valor")
                or normalized_row.get("amount")
                or normalized_row.get("vlr")
            )
            if not val_str:
                continue

            # Localizar descrição
            desc = (
                normalized_row.get("descricao")
                or normalized_row.get("historico")
                or normalized_row.get("memo")
                or normalized_row.get("description")
                or "Sem descrição"
            )

            # Normalização de valor brasileiro (ex: "1.250,50" -> 1250.50)
            cleaned_val = val_str.replace("R$", "").strip()
            if "," in cleaned_val and "." in cleaned_val:
                cleaned_val = cleaned_val.replace(".", "").replace(",", ".")
            elif "," in cleaned_val:
                cleaned_val = cleaned_val.replace(",", ".")

            try:
                val_decimal = Decimal(cleaned_val)
            except Exception:
                continue

            # Parsing de data flexível
            parsed_date = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    pass

            if not parsed_date:
                parsed_date = datetime.now()

            tipo = TipoMovimento.ENTRADA if val_decimal >= 0 else TipoMovimento.SAIDA
            items.append(
                ParsedTransactionItem(
                    data=parsed_date,
                    descricao=desc,
                    documento=normalized_row.get("documento") or normalized_row.get("doc"),
                    valor=abs(val_decimal),
                    tipo_movimento=tipo
                )
            )
        return StatementParseResult(transacoes=items)


class PDFParser(BaseParser):
    def parse(self, content: bytes) -> StatementParseResult:
        import pdfplumber
        items: List[ParsedTransactionItem] = []

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                for line in text.splitlines():
                    # Regex para capturar linhas de extrato típicas: Data | Descrição | Valor
                    match = re.search(r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?R?\$?\s*[\d\.,]+)$", line.strip())
                    if match:
                        dt_str, desc, val_str = match.groups()
                        try:
                            dt = datetime.strptime(dt_str, "%d/%m/%Y")
                            val_clean = val_str.replace("R$", "").replace(" ", "")
                            if "," in val_clean and "." in val_clean:
                                val_clean = val_clean.replace(".", "").replace(",", ".")
                            elif "," in val_clean:
                                val_clean = val_clean.replace(",", ".")
                            
                            val = Decimal(val_clean)
                            tipo = TipoMovimento.ENTRADA if val >= 0 else TipoMovimento.SAIDA
                            items.append(
                                ParsedTransactionItem(
                                    data=dt,
                                    descricao=desc.strip(),
                                    valor=abs(val),
                                    tipo_movimento=tipo
                                )
                            )
                        except Exception:
                            continue

        return StatementParseResult(transacoes=items)