"""Motor de Classificação em Cascata (Camadas 1 e 2)."""

import re
from typing import Optional, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Transacao,
    RegraClassificacao,
    OrigemClassificacao,
    StatusRevisao,
    CriterioRegra,
    PlanoContas,
    TipoMovimento
)
from backend.app.repositories.rule_repository import RuleRepository
from backend.app.repositories.transaction_repository import TransactionRepository


class ClassificationResult:
    def __init__(
        self,
        conta_id: Optional[int],
        origem: Optional[OrigemClassificacao],
        confianca: Decimal,
        justificativa: str
    ):
        self.conta_id = conta_id
        self.origem = origem
        self.confianca = confianca
        self.justificativa = justificativa


class RulesEngineService:
    """Aplica regras exatas (Camada 1) e regras de negócio contábil (Camada 2)."""

    def __init__(self, db: Session):
        self.db = db
        self.rule_repo = RuleRepository(db)
        self.tx_repo = TransactionRepository(db)

    def extract_document(self, text: str) -> Optional[str]:
        """Extrai CNPJ ou CPF presente no texto da transação."""
        cnpj_match = re.search(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", text)
        if cnpj_match:
            return cnpj_match.group(0)

        cpf_match = re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", text)
        if cpf_match:
            return cpf_match.group(0)

        return None

    def match_exact_rules(self, cliente_id: int, descricao: str) -> Optional[ClassificationResult]:
        """Camada 1: Correspondência exata por CNPJ/CPF ou substring de histórico cadastrado."""
        rule = self.rule_repo.find_matching_rule(cliente_id, descricao)
        if rule:
            return ClassificationResult(
                conta_id=rule.conta_id,
                origem=OrigemClassificacao.REGRA_EXATA,
                confianca=Decimal("1.00"),
                justificativa=f"Correspondência exata encontrada com critério: '{rule.valor_criterio}'"
            )
        return None

    def match_accounting_rules(
        self, cliente_id: int, descricao: str, tipo_movimento: TipoMovimento
    ) -> Optional[ClassificationResult]:
        """Camada 2: Regras contábeis padrão por termos bancários e radicais contábeis."""
        desc = descricao.upper()

        patterns = [
            (r"\b(TAR|TARIFA|TARIFAS)\b", "Despesa", "Tarif"),
            (r"\b(IOF)\b", "Despesa", "IOF"),
            (r"\b(REND|RENDIMENTO|RENDIMENTOS)\b", "Receita", "Rend"),
            (r"\b(RESGATE)\b", "Ativo", "Aplica"),
            (r"\b(GPS|INSS)\b", "Passivo", "INSS"),
            (r"\b(DARF|IMPOSTO|IMPOSTOS)\b", "Passivo", "Impost"),
            (r"\b(FGTS)\b", "Passivo", "FGTS"),
            (r"\b(SALARIO|SALARIOS|FOLHA)\b", "Despesa", "Salár"),
        ]

        for regex_pattern, tipo_esperado, search_stem in patterns:
            if re.search(regex_pattern, desc):
                conta = (
                    self.db.query(PlanoContas)
                    .filter(
                        PlanoContas.cliente_id == cliente_id,
                        PlanoContas.tipo.ilike(f"%{tipo_esperado}%"),
                        PlanoContas.descricao.ilike(f"%{search_stem}%")
                    )
                    .first()
                )
                if conta:
                    return ClassificationResult(
                        conta_id=conta.id,
                        origem=OrigemClassificacao.REGRA_CONTABIL,
                        confianca=Decimal("0.90"),
                        justificativa=f"Regra contábil aplicada via padrão '{regex_pattern}' -> Conta '{conta.descricao}'"
                    )

        return None

    def classify_transaction(self, transacao: Transacao) -> Transacao:
        """Executa a cascata de regras sobre uma única transação."""
        result = self.match_exact_rules(transacao.cliente_id, transacao.descricao_banco)

        if not result:
            result = self.match_accounting_rules(
                transacao.cliente_id, transacao.descricao_banco, transacao.tipo_movimento
            )

        if result:
            transacao.conta_classificada_id = result.conta_id
            transacao.origem_classificacao = result.origem
            transacao.confianca = result.confianca
            transacao.status_revisao = StatusRevisao.CONFIRMADO
        else:
            transacao.conta_classificada_id = None
            transacao.origem_classificacao = None
            transacao.confianca = Decimal("0.00")
            transacao.status_revisao = StatusRevisao.PENDENTE

        self.db.commit()
        self.db.refresh(transacao)
        return transacao

    def confirm_and_learn_rule(
        self, transacao_id: int, conta_id: int, criterio_texto: Optional[str] = None
    ) -> RegraClassificacao:
        """Aprende com a correção/confirmação humana, gerando uma regra da Camada 1."""
        tx = self.tx_repo.get_by_id(transacao_id)
        if not tx:
            raise ValueError(f"Transação {transacao_id} não encontrada.")

        termo = criterio_texto or tx.descricao_banco.strip()

        nova_regra = RegraClassificacao(
            cliente_id=tx.cliente_id,
            criterio=CriterioRegra.TEXTO,
            valor_criterio=termo,
            conta_id=conta_id
        )
        self.rule_repo.create(nova_regra)

        tx.conta_classificada_id = conta_id
        tx.origem_classificacao = OrigemClassificacao.MANUAL
        tx.confianca = Decimal("1.00")
        tx.status_revisao = StatusRevisao.REVISADO
        self.db.commit()

        return nova_regra
