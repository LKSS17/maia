"""Definição dos modelos relacionais do MAIA via SQLAlchemy 2.0."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
import enum
from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    ForeignKey,
    Enum,
    Integer,
    Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.session import Base


class TipoMovimento(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"


class OrigemClassificacao(str, enum.Enum):
    REGRA_EXATA = "regra_exata"
    REGRA_CONTABIL = "regra_contabil"
    IA = "ia"
    MANUAL = "manual"


class StatusRevisao(str, enum.Enum):
    PENDENTE = "pendente"
    CONFIRMADO = "confirmado"
    REVISADO = "revisado"


class CriterioRegra(str, enum.Enum):
    CNPJ = "cnpj"
    TEXTO = "texto"


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    documento: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    pasta_drive_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pasta_onedrive_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    plano_contas: Mapped[List["PlanoContas"]] = relationship("PlanoContas", back_populates="cliente", cascade="all, delete-orphan")
    transacoes: Mapped[List["Transacao"]] = relationship("Transacao", back_populates="cliente", cascade="all, delete-orphan")
    regras: Mapped[List["RegraClassificacao"]] = relationship("RegraClassificacao", back_populates="cliente", cascade="all, delete-orphan")
    extratos: Mapped[List["ExtratoImportado"]] = relationship("ExtratoImportado", back_populates="cliente", cascade="all, delete-orphan")


class PlanoContas(Base):
    __tablename__ = "plano_contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    numero_conta: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # Ex: Ativo, Passivo, Despesa, Receita

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="plano_contas")
    transacoes: Mapped[List["Transacao"]] = relationship("Transacao", back_populates="conta_classificada")
    regras: Mapped[List["RegraClassificacao"]] = relationship("RegraClassificacao", back_populates="conta")


class Transacao(Base):
    __tablename__ = "transacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    data: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    descricao_banco: Mapped[str] = mapped_column(String(500), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tipo_movimento: Mapped[TipoMovimento] = mapped_column(Enum(TipoMovimento), nullable=False)
    conta_classificada_id: Mapped[Optional[int]] = mapped_column(ForeignKey("plano_contas.id", ondelete="SET NULL"), nullable=True)
    origem_classificacao: Mapped[Optional[OrigemClassificacao]] = mapped_column(Enum(OrigemClassificacao), nullable=True)
    confianca: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2), nullable=True)  # De 0.00 a 1.00
    status_revisao: Mapped[StatusRevisao] = mapped_column(Enum(StatusRevisao), default=StatusRevisao.PENDENTE, nullable=False)

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="transacoes")
    conta_classificada: Mapped[Optional["PlanoContas"]] = relationship("PlanoContas", back_populates="transacoes")
    logs_auditoria: Mapped[List["LogAuditoria"]] = relationship("LogAuditoria", back_populates="transacao", cascade="all, delete-orphan")


class RegraClassificacao(Base):
    __tablename__ = "regras_classificacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    criterio: Mapped[CriterioRegra] = mapped_column(Enum(CriterioRegra), nullable=False)
    valor_criterio: Mapped[str] = mapped_column(String(255), nullable=False)
    conta_id: Mapped[int] = mapped_column(ForeignKey("plano_contas.id", ondelete="CASCADE"), nullable=False)

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="regras")
    conta: Mapped["PlanoContas"] = relationship("PlanoContas", back_populates="regras")


class ExtratoImportado(Base):
    __tablename__ = "extratos_importados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    hash_arquivo: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    data_importacao: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="extratos")


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transacao_id: Mapped[int] = mapped_column(ForeignKey("transacoes.id", ondelete="CASCADE"), nullable=False, index=True)
    acao: Mapped[str] = mapped_column(String(100), nullable=False)
    usuario: Mapped[str] = mapped_column(String(100), default="sistema", nullable=False)
    detalhes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    transacao: Mapped["Transacao"] = relationship("Transacao", back_populates="logs_auditoria")
