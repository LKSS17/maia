"""Módulo de classificação contábil residual via Gemini API."""

import json
import time
from typing import List, Dict, Any, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from google import genai
from google.genai import types

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.entities import (
    Transacao, PlanoContas, OrigemClassificacao, StatusRevisao, TipoMovimento
)
from backend.app.services.ai_dto import AIBatchResponse, AIClassificationItem


class GeminiClassifierService:
    """Cliente resiliente da API do Gemini para classificação de transações residuais."""

    def __init__(self, db: Session, client: Optional[genai.Client] = None):
        self.db = db
        self.api_key = settings.GEMINI_API_KEY
        self.client = client
        if not self.client and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        
        # Cache local por descrição normalizada para economizar cota de API
        self._local_cache: Dict[str, Dict[str, Any]] = {}

    def _normalize_text(self, text: str) -> str:
        return " ".join(text.upper().split())

    def _build_prompt(self, plano_contas: List[PlanoContas], transacoes: List[Transacao]) -> str:
        """Monta o prompt estruturado com contexto contábil estrito."""
        contas_txt = "\n".join([
            f"- ID: {c.id} | Conta: {c.numero_conta} | Nome: {c.descricao} | Tipo: {c.tipo}"
            for c in plano_contas
        ])

        txs_txt = "\n".join([
            f"- ID: {t.id} | Data: {t.data.strftime('%d/%m/%Y')} | Tipo: {t.tipo_movimento.value} | Valor: R$ {t.valor} | Histórico: {t.descricao_banco}"
            for t in transacoes
        ])

        prompt = f"""Você é um especialista contábil assistente do sistema MAIA.
Sua missão é classificar cada uma das transações bancárias abaixo atribuindo a melhor conta contábil do Plano de Contas fornecido.

REGRAS OBRIGATÓRIAS:
1. Para transações com TipoMovimento = 'SAIDA', sugira prioritariamente contas de Despesa, Custos ou Passivo.
2. Para transações com TipoMovimento = 'ENTRADA', sugira contas de Receita ou Ativo.
3. Utilize estritamente os IDs e Contas do Plano de Contas fornecido.
4. O score de confiança deve ser um decimal entre 0.00 e 1.00.
5. Retorne a resposta estritamente no formato JSON padronizado.

### PLANO DE CONTAS DISPONÍVEL:
{contas_txt}

### TRANSAÇÕES A CLASSIFICAR:
{txs_txt}
"""
        return prompt

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=10)
    )
    def _call_gemini_api(self, prompt: str) -> str:
        """Executa a chamada remota à API do Gemini com retry exponencial."""
        if not self.client:
            raise ValueError("Chave de API do Gemini não configurada.")

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AIBatchResponse,
                temperature=0.1
            ),
        )
        return response.text

    def classify_batch(
        self, cliente_id: int, transacoes_pendentes: List[Transacao]
    ) -> List[Transacao]:
        """Classifica um lote de transações residuais respeitando cache e rate limiting."""
        if not transacoes_pendentes:
            return []

        # 1. Recuperar plano de contas do cliente
        plano = self.db.query(PlanoContas).filter(PlanoContas.cliente_id == cliente_id).all()
        if not plano:
            logger.warning(f"Cliente {cliente_id} não possui plano de contas cadastrado.")
            return transacoes_pendentes

        plano_map = {c.id: c for c in plano}
        to_call: List[Transacao] = []

        # 2. Aplicar cache para transações com descrições idênticas
        for tx in transacoes_pendentes:
            norm_desc = self._normalize_text(tx.descricao_banco)
            if norm_desc in self._local_cache:
                cached = self._local_cache[norm_desc]
                tx.conta_classificada_id = cached["conta_id"]
                tx.origem_classificacao = OrigemClassificacao.IA
                tx.confianca = cached["confianca"]
                tx.status_revisao = StatusRevisao.CONFIRMADO if tx.confianca >= Decimal("0.85") else StatusRevisao.PENDENTE
            else:
                to_call.append(tx)

        if not to_call:
            self.db.commit()
            return transacoes_pendentes

        # 3. Execução em lote via Gemini API (lotes de até 15 itens)
        batch_size = 15
        for i in range(0, len(to_call), batch_size):
            chunk = to_call[i:i + batch_size]
            prompt = self._build_prompt(plano, chunk)

            try:
                raw_json = self._call_gemini_api(prompt)
                parsed = AIBatchResponse.model_validate_json(raw_json)

                res_map = {item.transacao_id: item for item in parsed.classificacoes}

                for tx in chunk:
                    if tx.id in res_map:
                        item = res_map[tx.id]
                        if item.conta_id in plano_map:
                            tx.conta_classificada_id = item.conta_id
                            tx.origem_classificacao = OrigemClassificacao.IA
                            tx.confianca = item.confianca
                            
                            # Confiança alta classifica direto; confiança baixa vai para revisão manual
                            if tx.confianca >= Decimal("0.85"):
                                tx.status_revisao = StatusRevisao.CONFIRMADO
                            else:
                                tx.status_revisao = StatusRevisao.PENDENTE

                            # Salvar no cache local
                            norm_desc = self._normalize_text(tx.descricao_banco)
                            self._local_cache[norm_desc] = {
                                "conta_id": item.conta_id,
                                "confianca": item.confianca
                            }
            except Exception as e:
                logger.error(f"Falha ao classificar lote via IA: {str(e)}")
                # Modo degradado: as transações continuam pendentes sem interromper o sistema
                for tx in chunk:
                    tx.status_revisao = StatusRevisao.PENDENTE

            # Pequena pausa para respeitar limites do free tier
            time.sleep(0.5)

        self.db.commit()
        return transacoes_pendentes
