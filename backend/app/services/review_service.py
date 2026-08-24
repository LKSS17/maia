"""Serviço de human-in-the-loop: listagem, aprovação e correção de lançamentos."""

from typing import List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Transacao, PlanoContas, StatusRevisao, OrigemClassificacao
)
from backend.app.repositories.transaction_repository import TransactionRepository
from backend.app.repositories.audit_repository import AuditRepository
from backend.app.services.rules_engine import RulesEngineService
from backend.app.services.review_dto import ReviewItemDTO, ManualCorrectionRequest


class ReviewService:
    """Gerencia a fila de revisão humana e auditoria de ações contábeis."""

    def __init__(self, db: Session):
        self.db = db
        self.tx_repo = TransactionRepository(db)
        self.audit_repo = AuditRepository(db)
        self.rules_engine = RulesEngineService(db)

    def _determine_confidence_level(self, confianca: Optional[Decimal]) -> str:
        if not confianca or confianca < Decimal("0.50"):
            return "BAIXA"
        elif confianca < Decimal("0.85"):
            return "MEDIA"
        return "ALTA"

    def get_pending_review_items(self, cliente_id: int) -> List[ReviewItemDTO]:
        """Recupera transações que exigem atenção humana."""
        txs = (
            self.db.query(Transacao)
            .filter(
                Transacao.cliente_id == cliente_id,
                Transacao.status_revisao == StatusRevisao.PENDENTE
            )
            .order_by(Transacao.data.asc())
            .all()
        )

        items: List[ReviewItemDTO] = []
        for t in txs:
            items.append(
                ReviewItemDTO(
                    id=t.id,
                    data=t.data.date() if hasattr(t.data, "date") else t.data,
                    descricao_banco=t.descricao_banco,
                    valor=t.valor,
                    tipo_movimento=t.tipo_movimento,
                    conta_id=t.conta_classificada_id,
                    numero_conta=t.conta_classificada.numero_conta if t.conta_classificada else None,
                    descricao_conta=t.conta_classificada.descricao if t.conta_classificada else None,
                    origem=t.origem_classificacao,
                    confianca=t.confianca or Decimal("0.00"),
                    nivel_confianca=self._determine_confidence_level(t.confianca),
                    status_revisao=t.status_revisao
                )
            )
        return items

    def approve_transaction(self, transacao_id: int, usuario: str = "usuaria") -> Transacao:
        """Aprova a classificação sugerida pela IA ou regra prévia."""
        tx = self.tx_repo.get_by_id(transacao_id)
        if not tx:
            raise ValueError(f"Transação {transacao_id} não encontrada.")
        if not tx.conta_classificada_id:
            raise ValueError(f"Não é possível aprovar uma transação sem conta atribuída.")

        tx.status_revisao = StatusRevisao.CONFIRMADO
        self.db.commit()

        self.audit_repo.log_action(
            transacao_id=tx.id,
            acao="APROVACAO",
            usuario=usuario,
            detalhes=f"Aprovado lançamento na conta ID {tx.conta_classificada_id} (origem: {tx.origem_classificacao})"
        )
        return tx

    def approve_batch(self, transacao_ids: List[int], usuario: str = "usuaria") -> int:
        """Aprova múltiplos itens de uma só vez."""
        count = 0
        for tid in transacao_ids:
            try:
                self.approve_transaction(tid, usuario)
                count += 1
            except Exception:
                continue
        return count

    def correct_manually(self, request: ManualCorrectionRequest) -> Transacao:
        """Aplica correção manual e, se solicitado, grava a nova regra de negócio."""
        tx = self.tx_repo.get_by_id(request.transacao_id)
        if not tx:
            raise ValueError(f"Transação {request.transacao_id} não encontrada.")

        conta = self.db.query(PlanoContas).filter(PlanoContas.id == request.nova_conta_id).first()
        if not conta:
            raise ValueError(f"Conta contábil {request.nova_conta_id} não encontrada.")

        old_account_id = tx.conta_classificada_id

        if request.salvar_como_regra:
            self.rules_engine.confirm_and_learn_rule(
                transacao_id=tx.id,
                conta_id=request.nova_conta_id,
                criterio_texto=request.criterio_texto
            )
        else:
            tx.conta_classificada_id = request.nova_conta_id
            tx.origem_classificacao = OrigemClassificacao.MANUAL
            tx.confianca = Decimal("1.00")
            tx.status_revisao = StatusRevisao.REVISADO
            self.db.commit()

        self.audit_repo.log_action(
            transacao_id=tx.id,
            acao="CORRECAO_MANUAL",
            usuario=request.usuario,
            detalhes=f"Conta alterada de {old_account_id} para {conta.id} ({conta.descricao}). Regra criada: {request.salvar_como_regra}"
        )
        return tx
