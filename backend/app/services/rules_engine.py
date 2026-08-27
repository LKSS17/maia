"""Motor de Regras Contábeis com suporte a Lote (Batch) e Classificação Unitária com compatibilidade."""

import re
from decimal import Decimal
from typing import List, Optional, Callable
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Transacao, RegraClassificacao, StatusRevisao, 
    OrigemClassificacao, CriterioRegra
)
from backend.app.repositories.regra_repository import RegraRepository
from backend.app.repositories.plano_contas_repository import PlanoContasRepository


class RulesEngineService:
    def __init__(self, db: Session):
        self.db = db
        self.regra_repo = RegraRepository(db)
        self.plano_repo = PlanoContasRepository(db)

    def _normalize(self, text: str) -> str:
        return " ".join(text.upper().split())

    def classify_transaction(self, tx: Transacao) -> Transacao:
        """Classifica uma transação individual mantendo compatibilidade com métodos legados."""
        self.classify_batch(tx.cliente_id, [tx])
        return tx

    def classify_batch(
        self, 
        cliente_id: int, 
        transacoes: List[Transacao],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Transacao]:
        """Classifica uma lista de transações com regras pré-carregadas na memória."""
        if not transacoes:
            return []

        regras_ativas = self.regra_repo.list_by_client(cliente_id)
        plano_contas = self.plano_repo.list_by_cliente(cliente_id)
        
        contas_por_termo = {}
        for c in plano_contas:
            contas_por_termo[self._normalize(c.descricao)] = c.id

        total = len(transacoes)
        checkpoint_size = 100

        for idx, tx in enumerate(transacoes, start=1):
            desc_norm = self._normalize(tx.descricao_banco)
            classificado = False

            # Camada 1: Regras do Cliente
            for regra in regras_ativas:
                padrao_norm = self._normalize(regra.padrao)
                if regra.criterio == CriterioRegra.CNPJ and padrao_norm in desc_norm:
                    tx.conta_classificada_id = regra.conta_destino_id
                    tx.origem_classificacao = OrigemClassificacao.REGRA_EXATA
                    tx.confianca = Decimal("1.00")
                    tx.status_revisao = StatusRevisao.CONFIRMADO
                    classificado = True
                    break
                elif regra.criterio == CriterioRegra.TERMO_EXATO and padrao_norm == desc_norm:
                    tx.conta_classificada_id = regra.conta_destino_id
                    tx.origem_classificacao = OrigemClassificacao.REGRA_EXATA
                    tx.confianca = Decimal("1.00")
                    tx.status_revisao = StatusRevisao.CONFIRMADO
                    classificado = True
                    break
                elif regra.criterio == CriterioRegra.CONFORME and padrao_norm in desc_norm:
                    tx.conta_classificada_id = regra.conta_destino_id
                    tx.origem_classificacao = OrigemClassificacao.REGRA_PADRAO
                    tx.confianca = Decimal("0.90")
                    tx.status_revisao = StatusRevisao.CONFIRMADO
                    classificado = True
                    break

            # Camada 2: Regras Contábeis Globais
            if not classificado:
                if any(k in desc_norm for k in ["IOF", "TARIFA", "MANUTENCAO CONTA", "TAXA"]):
                    for desc, cid in contas_por_termo.items():
                        if "DESPESAS BANCARIAS" in desc or "TARIFA" in desc:
                            tx.conta_classificada_id = cid
                            tx.origem_classificacao = OrigemClassificacao.REGRA_PADRAO
                            tx.confianca = Decimal("0.85")
                            tx.status_revisao = StatusRevisao.CONFIRMADO
                            classificado = True
                            break

                elif any(k in desc_norm for k in ["RENDIMENTO", "APLICACAO", "RESGATE", "JUROS S/ CAPITAL"]):
                    for desc, cid in contas_por_termo.items():
                        if "RECEITA FINANCEIRA" in desc or "RENDIMENTO" in desc:
                            tx.conta_classificada_id = cid
                            tx.origem_classificacao = OrigemClassificacao.REGRA_PADRAO
                            tx.confianca = Decimal("0.85")
                            tx.status_revisao = StatusRevisao.CONFIRMADO
                            classificado = True
                            break

            if not classificado:
                tx.status_revisao = StatusRevisao.PENDENTE

            if idx % checkpoint_size == 0:
                self.db.commit()

            if progress_callback:
                progress_callback(idx, total)

        self.db.commit()
        return transacoes