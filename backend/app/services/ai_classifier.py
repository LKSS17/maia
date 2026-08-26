"""Serviço de classificação de lançamentos via Google GenAI SDK (novo) com schema Pydantic, retry e cache desacoplado de sessão."""

import json
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from google import genai
from google.genai import types

from backend.app.models.entities import Transacao, PlanoContas, StatusRevisao, OrigemClassificacao
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.ai_dto import AIBatchResponse, AIClassificationItem


class GeminiClassifierService:
    """Classificador com cache de longa duração por radical e fallback com retry."""

    CONFIDENCE_THRESHOLD = Decimal("0.85")

    def __init__(self):
        self._local_cache: Dict[str, Dict[str, Any]] = {}

    def _normalize_key(self, text: str) -> str:
        return " ".join(text.upper().split())

    def _apply_classification(self, tx: Transacao, conta_id: Optional[int], confianca: Decimal):
        """Aplica a conta, calcula o status de revisão com base no limiar e define a origem."""
        tx.conta_classificada_id = conta_id
        tx.origem_classificacao = OrigemClassificacao.IA
        tx.confianca = confianca
        if confianca >= self.CONFIDENCE_THRESHOLD and conta_id is not None:
            tx.status_revisao = StatusRevisao.CONFIRMADO
        else:
            tx.status_revisao = StatusRevisao.PENDENTE

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    def _call_gemini_api(self, prompt: str) -> AIBatchResponse:
        """Invoca o modelo com tipagem estruturada via SDK google-genai."""
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AIBatchResponse,
                temperature=0.1
            )
        )
        return AIBatchResponse.model_validate_json(response.text)

    def classify_batch(self, db: Session, cliente_id: int, transacoes: List[Transacao]) -> List[Transacao]:
        """Classifica lote de transações usando cache em memória ou invocando o Gemini com garantia de persistência."""
        if not transacoes or db is None:
            return transacoes

        pendentes_api: List[Transacao] = []

        # 1. Processar itens existentes no cache
        for tx in transacoes:
            key = self._normalize_key(tx.descricao_banco)
            if key in self._local_cache:
                cached = self._local_cache[key]
                conta_id = cached.get("conta_id")
                confianca = Decimal(str(cached.get("confianca", "0.80")))
                self._apply_classification(tx, conta_id, confianca)
            else:
                pendentes_api.append(tx)

        # Commit imediato dos itens resolvidos via cache
        try:
            db.commit()
        except Exception as e:
            logger.error(f"Erro ao commitar transações resolvidas via cache: {e}")
            db.rollback()

        if not pendentes_api:
            return transacoes

        # 2. Se não houver API key configurada, mantém pendentes para revisão humana
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY não configurada. Transações residuais mantidas como pendentes para revisão.")
            return transacoes

        # 3. Classificação remota via Gemini 2.5 Flash
        try:
            plano_contas = db.query(PlanoContas).filter(PlanoContas.cliente_id == cliente_id).all()
            contas_str = "\n".join([f"- ID {c.id}: {c.numero_conta} {c.descricao} ({c.tipo})" for c in plano_contas])

            itens_prompt = [
                {"index": idx, "descricao": tx.descricao_banco, "valor": float(tx.valor), "tipo": tx.tipo_movimento.value}
                for idx, tx in enumerate(pendentes_api)
            ]

            prompt = f"""
Você é um assistente contábil sênior. Classifique as transações bancárias abaixo associando cada uma ao melhor ID do Plano de Contas fornecido.

Plano de Contas Disponível:
{contas_str}

Transações para Classificar:
{json.dumps(itens_prompt, ensure_ascii=False)}
"""
            batch_result = self._call_gemini_api(prompt)

            for item in batch_result.classificacoes:
                idx = item.index
                if idx is not None and 0 <= idx < len(pendentes_api):
                    tx = pendentes_api[idx]
                    conta_id = item.conta_id
                    confianca = Decimal(str(item.confianca))

                    self._apply_classification(tx, conta_id, confianca)

                    # Atualizar cache de longa duração
                    key = self._normalize_key(tx.descricao_banco)
                    self._local_cache[key] = {
                        "conta_id": conta_id,
                        "confianca": float(confianca)
                    }

            db.commit()

        except Exception as e:
            logger.error(f"Falha na classificação via IA Gemini: {str(e)}")
            db.rollback()

        return transacoes