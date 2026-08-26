"""Serviço de classificação de lançamentos via Google Gemini API com cache em memória desacoplado de sessão."""

import json
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.models.entities import Transacao, PlanoContas, StatusRevisao, OrigemClassificacao
from backend.app.core.config import settings
from backend.app.core.logging import logger


class GeminiClassifierService:
    """Classificador com cache de longa duração por radical de texto."""

    def __init__(self):
        self._local_cache: Dict[str, Dict[str, Any]] = {}

    def _normalize_key(self, text: str) -> str:
        return " ".join(text.upper().split())

    def classify_batch(self, db: Session, cliente_id: int, transacoes: List[Transacao]) -> List[Transacao]:
        """Classifica lote de transações usando cache local ou invocando a API do Gemini.
        
        A sessão do SQLAlchemy é recebida estritamente por parâmetro para garantir thread-safety.
        """
        if not transacoes or db is None:
            return transacoes

        pendentes_api: List[Transacao] = []

        # 1. Checar cache da instância
        for tx in transacoes:
            key = self._normalize_key(tx.descricao_banco)
            if key in self._local_cache:
                cached = self._local_cache[key]
                tx.conta_classificada_id = cached.get("conta_id")
                tx.origem_classificacao = OrigemClassificacao.IA
                tx.confianca = Decimal(str(cached.get("confianca", 0.80)))
                tx.status_revisao = StatusRevisao.PENDENTE
            else:
                pendentes_api.append(tx)

        if not pendentes_api:
            db.commit()
            return transacoes

        # 2. Se a API Key não estiver configurada, deixa como pendente sem erro fatal
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY não configurada. Transações residuais mantidas para revisão humana.")
            return transacoes

        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")

            plano_contas = db.query(PlanoContas).filter(PlanoContas.cliente_id == cliente_id).all()
            contas_str = "\n".join([f"- ID {c.id}: {c.numero_conta} {c.descricao} ({c.tipo})" for c in plano_contas])

            itens_prompt = [
                {"index": idx, "descricao": tx.descricao_banco, "valor": float(tx.valor), "tipo": tx.tipo_movimento.value}
                for idx, tx in enumerate(pendentes_api)
            ]

            prompt = f"""
Você é um assistente contábil sênior. Classifique as transações bancárias abaixo associando-as ao melhor ID do Plano de Contas fornecido.

Plano de Contas Disponível:
{contas_str}

Transações para Classificar:
{json.dumps(itens_prompt, ensure_ascii=False)}

Retorne EXCLUSIVAMENTE um array JSON no seguinte formato:
[
  {{"index": 0, "conta_id": 123, "confianca": 0.85, "justificativa": "Motivo contábil..."}}
]
"""
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            classificacoes = json.loads(response.text)

            for item in classificacoes:
                idx = item.get("index")
                if idx is not None and idx < len(pendentes_api):
                    tx = pendentes_api[idx]
                    conta_id = item.get("conta_id")
                    confianca = Decimal(str(item.get("confianca", 0.70)))

                    tx.conta_classificada_id = conta_id
                    tx.origem_classificacao = OrigemClassificacao.IA
                    tx.confianca = confianca
                    tx.status_revisao = StatusRevisao.PENDENTE

                    # Guardar no cache da instância
                    key = self._normalize_key(tx.descricao_banco)
                    self._local_cache[key] = {
                        "conta_id": conta_id,
                        "confianca": float(confianca)
                    }

            db.commit()

        except Exception as e:
            logger.error(f"Falha na classificação via IA Gemini: {str(e)}")

        return transacoes