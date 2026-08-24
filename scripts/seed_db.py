"""Popula o banco com dados de exemplo para validação."""

from decimal import Decimal
from datetime import datetime
from backend.app.db.session import SessionLocal, Base, engine
from backend.app.models.entities import (
    Cliente, PlanoContas, Transacao, RegraClassificacao,
    TipoMovimento, StatusRevisao, CriterioRegra, OrigemClassificacao
)


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(Cliente).first():
        print("Banco já possui registros. Seed abortado.")
        db.close()
        return

    # 1. Cliente
    cliente = Cliente(nome="Empresa Exemplo LTDA", documento="12.345.678/0001-90")
    db.add(cliente)
    db.commit()
    db.refresh(cliente)

    # 2. Plano de Contas
    c1 = PlanoContas(cliente_id=cliente.id, numero_conta="1.1.1.01", descricao="Caixa / Banco", tipo="Ativo")
    c2 = PlanoContas(cliente_id=cliente.id, numero_conta="3.1.1.01", descricao="Receita de Serviços", tipo="Receita")
    c3 = PlanoContas(cliente_id=cliente.id, numero_conta="4.1.2.01", descricao="Despesa de Energia Elétrica", tipo="Despesa")
    db.add_all([c1, c2, c3])
    db.commit()
    db.refresh(c3)

    # 3. Regra de Classificação
    regra = RegraClassificacao(
        cliente_id=cliente.id,
        criterio=CriterioRegra.TEXTO,
        valor_criterio="ENEL",
        conta_id=c3.id
    )
    db.add(regra)

    # 4. Transação
    t1 = Transacao(
        cliente_id=cliente.id,
        data=datetime.now(),
        descricao_banco="PAGTO ENEL DISTRIBUICAO",
        valor=Decimal("250.50"),
        tipo_movimento=TipoMovimento.SAIDA,
        conta_classificada_id=c3.id,
        origem_classificacao=OrigemClassificacao.REGRA_EXATA,
        confianca=Decimal("1.00"),
        status_revisao=StatusRevisao.CONFIRMADO
    )
    db.add(t1)
    db.commit()

    print("Seed executado com sucesso!")
    db.close()


if __name__ == "__main__":
    seed()
