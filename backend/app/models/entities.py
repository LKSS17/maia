"""Modelos de banco de dados do MAIA com índices compostos otimizados para SQLAlchemy 2.0."""

import enum
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    String, Integer, Numeric, DateTime, Enum, ForeignKey, 
    Boolean, Text, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


class TipoMovimento(str, enum.Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"


class StatusRevisao(str, enum.Enum):
    PENDENTE = "pendente"
    CONFIRMADO = "confirmado"


class OrigemClassificacao(str, enum.Enum):
    REGRA_EXATA = "regra_exata"
    REGRA_PADRAO = "regra_padrao"
    IA = "ia"
    MANUAL = "manual"
    SEM_CLASSIFICACAO = "sem_classificacao"


class CriterioRegra(str, enum.Enum):
    CNPJ = "cnpj"
    TERMO_EXATO = "termo_exato"
    CONFORME = "conforme"


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    documento: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    planos_contas: Mapped[List["PlanoContas"]] = relationship(back_populates="cliente", cascade="all, delete-orphan")
    extratos: Mapped[List["Extrato"]] = relationship(back_populates="cliente", cascade="all, delete-orphan")
    transacoes: Mapped[List["Transacao"]] = relationship(back_populates="cliente", cascade="all, delete-orphan")
    regras: Mapped[List["RegraClassificacao"]] = relationship(back_populates="cliente", cascade="all, delete-orphan")


class PlanoContas(Base):
    __tablename__ = "planos_contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False)
    numero_conta: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)

    cliente: Mapped["Cliente"] = relationship(back_populates="planos_contas")
    transacoes: Mapped[List["Transacao"]] = relationship(back_populates="conta_classificada")
    regras: Mapped[List["RegraClassificacao"]] = relationship(back_populates="conta_destino")


class Extrato(Base):
    __tablename__ = "extratos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    total_transacoes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship(back_populates="extratos")
    transacoes: Mapped[List["Transacao"]] = relationship(back_populates="extrato", cascade="all, delete-orphan")


class Transacao(Base):
    __tablename__ = "transacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    extrato_id: Mapped[int] = mapped_column(Integer, ForeignKey("extratos.id"), nullable=False)
    data: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    descricao_banco: Mapped[str] = mapped_column(String(500), nullable=False)
    documento: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tipo_movimento: Mapped[TipoMovimento] = mapped_column(Enum(TipoMovimento), nullable=False)
    
    conta_classificada_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("planos_contas.id"), nullable=True)
    origem_classificacao: Mapped[OrigemClassificacao] = mapped_column(
        Enum(OrigemClassificacao), default=OrigemClassificacao.SEM_CLASSIFICACAO
    )
    confianca: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.00"))
    status_revisao: Mapped[StatusRevisao] = mapped_column(
        Enum(StatusRevisao), default=StatusRevisao.PENDENTE, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship(back_populates="transacoes")
    extrato: Mapped["Extrato"] = relationship(back_populates="transacoes")
    conta_classificada: Mapped[Optional["PlanoContas"]] = relationship(back_populates="transacoes")


class RegraClassificacao(Base):
    __tablename__ = "regras_classificacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    criterio: Mapped[CriterioRegra] = mapped_column(Enum(CriterioRegra), nullable=False)
    padrao: Mapped[str] = mapped_column(String(255), nullable=False)
    conta_destino_id: Mapped[int] = mapped_column(Integer, ForeignKey("planos_contas.id"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship(back_populates="regras")
    conta_destino: Mapped["PlanoContas"] = relationship(back_populates="regras")


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transacao_id: Mapped[int] = mapped_column(Integer, ForeignKey("transacoes.id"), nullable=False, index=True)
    acao: Mapped[str] = mapped_column(String(100), nullable=False)
    detalhes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usuario: Mapped[str] = mapped_column(String(100), default="sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)