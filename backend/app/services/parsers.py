"""Implementação dos parsers de extrato bancário para OFX, CSV e PDF."""

import io
import re
import csv
import chardet
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List
from ofxparse import OfxParser as VendorOfxParser
import pdfplumber

from backend.app.models.entities import TipoMovimento
from backend.app.services.statement_dto import ParsedTransaction


class BaseParser(ABC):
    """Interface abstrata para parsers de extratos bancários."""

    @abstractmethod
    def parse(self, content_bytes: bytes, filename: str) -> List[ParsedTransaction]:
        pass


class OfxParser(BaseParser):
    """Parser para arquivos no padrão OFX."""

    def parse(self, content_bytes: bytes, filename: str) -> List[ParsedTransaction]:
        stream = io.BytesIO(content_bytes)
        try:
            ofx = VendorOfxParser.parse(stream)
        except Exception as e:
            raise ValueError(f"Falha ao processar arquivo OFX: {str(e)}")

        transactions: List[ParsedTransaction] = []
        if not ofx.account or not ofx.account.statement:
            return transactions

        for tx in ofx.account.statement.transactions:
            val = Decimal(str(tx.amount))
            tipo = TipoMovimento.ENTRADA if val > 0 else TipoMovimento.SAIDA
            abs_val = abs(val)

            transactions.append(
                ParsedTransaction(
                    data=tx.date.date(),
                    descricao=(tx.memo or tx.payee or "TRANSACAO SEM DESCRICAO").strip(),
                    valor=abs_val,
                    tipo_movimento=tipo,
                    fitid=tx.id,
                    confianca_extracao=Decimal("1.00")
                )
            )

        return transactions


class CsvParser(BaseParser):
    """Parser flexível para extratos bancários em formato CSV."""

    def parse(self, content_bytes: bytes, filename: str) -> List[ParsedTransaction]:
        encoding_detect = chardet.detect(content_bytes)
        encoding = encoding_detect["encoding"] or "utf-8"
        text = content_bytes.decode(encoding, errors="replace")

        # Detectar delimitador (vírgula ou ponto e vírgula)
        sample = text[:2048]
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [row for row in reader if any(field.strip() for field in row)]

        if not rows:
            return []

        # Localizar linha de cabeçalho
        header_idx = -1
        col_map = {}
        for idx, row in enumerate(rows[:10]):
            normalized_row = [c.lower().strip() for c in row]
            for col_i, col_name in enumerate(normalized_row):
                if any(k in col_name for k in ["data", "dt", "date"]):
                    col_map["data"] = col_i
                elif any(k in col_name for k in ["historico", "descri", "memo", "detalhe", "lancamento"]):
                    col_map["descricao"] = col_i
                elif any(k in col_name for k in ["valor", "val", "amount", "quantia"]):
                    col_map["valor"] = col_i
                elif "debito" in col_name or "saida" in col_name:
                    col_map["debito"] = col_i
                elif "credito" in col_name or "entrada" in col_name:
                    col_map["credito"] = col_i

            if "data" in col_map and ("valor" in col_map or "debito" in col_map or "credito" in col_map):
                header_idx = idx
                break

        if header_idx == -1:
            raise ValueError("Não foi possível identificar as colunas obrigatórias no arquivo CSV.")

        transactions: List[ParsedTransaction] = []
        date_formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]

        for row in rows[header_idx + 1:]:
            if not row or len(row) <= max(col_map.values()):
                continue

            raw_date = row[col_map["data"]].strip()
            parsed_date = None
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue

            if not parsed_date:
                continue

            desc_idx = col_map.get("descricao")
            desc = row[desc_idx].strip() if desc_idx is not None and desc_idx < len(row) else "TRANSACAO CSV"

            # Resolução de Valor e Tipo de Movimento
            valor = Decimal("0.00")
            tipo = TipoMovimento.SAIDA

            try:
                if "valor" in col_map:
                    raw_val_str = row[col_map["valor"]].replace("R$", "").replace(".", "").replace(",", ".").strip()
                    raw_val = Decimal(raw_val_str)
                    tipo = TipoMovimento.ENTRADA if raw_val > 0 else TipoMovimento.SAIDA
                    valor = abs(raw_val)
                elif "debito" in col_map and row[col_map["debito"]].strip():
                    raw_val_str = row[col_map["debito"]].replace("R$", "").replace(".", "").replace(",", ".").strip()
                    valor = abs(Decimal(raw_val_str))
                    tipo = TipoMovimento.SAIDA
                elif "credito" in col_map and row[col_map["credito"]].strip():
                    raw_val_str = row[col_map["credito"]].replace("R$", "").replace(".", "").replace(",", ".").strip()
                    valor = abs(Decimal(raw_val_str))
                    tipo = TipoMovimento.ENTRADA
            except (InvalidOperation, ValueError):
                continue

            if valor > 0:
                transactions.append(
                    ParsedTransaction(
                        data=parsed_date,
                        descricao=desc,
                        valor=valor,
                        tipo_movimento=tipo,
                        confianca_extracao=Decimal("1.00")
                    )
                )

        return transactions


class PdfParser(BaseParser):
    """Parser para extratos em PDF com extração baseada em texto."""

    def parse(self, content_bytes: bytes, filename: str) -> List[ParsedTransaction]:
        transactions: List[ParsedTransaction] = []
        stream = io.BytesIO(content_bytes)

        try:
            with pdfplumber.open(stream) as pdf:
                full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
        except Exception as e:
            raise ValueError(f"Falha ao ler arquivo PDF: {str(e)}")

        line_regex = re.compile(
            r"(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}/\d{2})\s+(.+?)\s+([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})\s*([DC]?)",
            re.IGNORECASE
        )

        for line in full_text.splitlines():
            line_str = line.strip()
            match = line_regex.search(line_str)
            if not match:
                continue

            raw_date, raw_desc, raw_val, signal_indicator = match.groups()

            # Normalização de Data
            parsed_date = None
            for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue

            if not parsed_date:
                continue

            # Normalização de Valor
            val_clean = raw_val.replace(" ", "").replace(".", "").replace(",", ".")
            try:
                val_dec = Decimal(val_clean)
            except InvalidOperation:
                continue

            abs_val = abs(val_dec)
            if signal_indicator.upper() == "C" or "+" in raw_val:
                tipo = TipoMovimento.ENTRADA
            elif signal_indicator.upper() == "D" or "-" in raw_val or val_dec < 0:
                tipo = TipoMovimento.SAIDA
            else:
                # Caso ambíguo em PDF: marca confiança menor para validação visual
                tipo = TipoMovimento.SAIDA

            transactions.append(
                ParsedTransaction(
                    data=parsed_date,
                    descricao=raw_desc.strip(),
                    valor=abs_val,
                    tipo_movimento=tipo,
                    confianca_extracao=Decimal("0.80"),
                    aviso_extracao="Extraído via PDF: confirmar valores e tipo de movimento."
                )
            )

        return transactions
