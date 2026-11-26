from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Double, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from alertalar.modelos.enums import (
    CategoriaFator,
    ClassificacaoRisco,
    NivelLocalizacao,
    OrigemOcorrencia,
    PapelUsuario,
    PrecisaoGeocodificacao,
    SituacaoFator,
    StatusIntegracao,
    StatusValidacao,
    TipoEvento,
    TipoFonte,
)


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _enum(classe, tamanho: int):
    return SqlEnum(classe, native_enum=False, create_constraint=False, length=tamanho, validate_strings=True)


class Base(DeclarativeBase):
    pass


class FonteDados(Base):
    __tablename__ = "fonte_dados"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[TipoFonte] = mapped_column(_enum(TipoFonte, 30))
    url: Mapped[str | None] = mapped_column(String(500))
    status_integracao: Mapped[StatusIntegracao] = mapped_column(_enum(StatusIntegracao, 30))
    oficial: Mapped[bool] = mapped_column(Boolean, default=False)
    data_atualizacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    descricao: Mapped[str | None] = mapped_column(String(1000))
    atribuicao: Mapped[str | None] = mapped_column(String(500))


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    senha_hash: Mapped[str] = mapped_column(String(100))
    papel: Mapped[PapelUsuario] = mapped_column(_enum(PapelUsuario, 20), default=PapelUsuario.USUARIO)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    data_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Endereco(Base):
    __tablename__ = "endereco"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cep: Mapped[str | None] = mapped_column(String(9))
    rua: Mapped[str | None] = mapped_column(String(200))
    numero: Mapped[str | None] = mapped_column(String(20))
    bairro: Mapped[str | None] = mapped_column(String(120))
    cidade: Mapped[str] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(String(2))
    codigo_ibge: Mapped[str | None] = mapped_column(String(7))
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    precisao: Mapped[PrecisaoGeocodificacao] = mapped_column(_enum(PrecisaoGeocodificacao, 20))
    fonte_geocodificacao: Mapped[str | None] = mapped_column(String(60))
    chave_normalizada: Mapped[str | None] = mapped_column(String(500))
    data_geocodificacao: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    def descricao_completa(self) -> str:
        partes = ""
        if self.rua and self.rua.strip():
            partes = self.rua
            if self.numero and self.numero.strip():
                partes += ", " + self.numero
        if self.bairro and self.bairro.strip():
            if partes:
                partes += " - "
            partes += self.bairro
        if partes:
            partes += ", "
        partes += f"{self.cidade}/{self.estado}"
        if self.cep and self.cep.strip():
            partes += " - CEP " + self.cep
        return partes


class Consulta(Base):
    __tablename__ = "consulta"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    endereco_id: Mapped[int] = mapped_column(ForeignKey("endereco.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    classificacao: Mapped[ClassificacaoRisco] = mapped_column(_enum(ClassificacaoRisco, 30))
    indice: Mapped[float | None] = mapped_column(Double)
    justificativa: Mapped[str] = mapped_column(Text)
    versao_metodologia: Mapped[str] = mapped_column(String(10))
    dados_mapa: Mapped[str | None] = mapped_column(Text)
    data_consulta: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    endereco: Mapped[Endereco] = relationship()
    fatores: Mapped[list[FatorConsulta]] = relationship(
        back_populates="consulta", cascade="all, delete-orphan", order_by="FatorConsulta.ordem")

    def adicionar_fator(self, fator: FatorConsulta) -> None:
        self.fatores.append(fator)


class FatorConsulta(Base):
    __tablename__ = "consulta_fator"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    consulta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consulta.id"))
    ordem: Mapped[int] = mapped_column(Integer)
    codigo: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[CategoriaFator] = mapped_column(_enum(CategoriaFator, 30))
    situacao: Mapped[SituacaoFator] = mapped_column(_enum(SituacaoFator, 20))
    pontuacao: Mapped[int | None] = mapped_column(Integer)
    peso: Mapped[float] = mapped_column(Double)
    valor_observado: Mapped[str | None] = mapped_column(String(500))
    explicacao: Mapped[str] = mapped_column(String(2000))
    fonte_id: Mapped[int | None] = mapped_column(ForeignKey("fonte_dados.id"))
    data_referencia: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    consulta: Mapped[Consulta] = relationship(back_populates="fatores")
    fonte: Mapped[FonteDados | None] = relationship()


class Ocorrencia(Base):
    __tablename__ = "ocorrencia"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    endereco_id: Mapped[int | None] = mapped_column(ForeignKey("endereco.id"))
    localizacao: Mapped[str] = mapped_column(String(300))
    municipio: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str | None] = mapped_column(String(2))
    codigo_ibge: Mapped[str | None] = mapped_column(String(7))
    data_ocorrencia: Mapped[date] = mapped_column(Date)
    descricao: Mapped[str] = mapped_column(String(2000))
    tipo_evento: Mapped[TipoEvento] = mapped_column(_enum(TipoEvento, 20))
    origem: Mapped[OrigemOcorrencia] = mapped_column(_enum(OrigemOcorrencia, 20))
    status_validacao: Mapped[StatusValidacao] = mapped_column(_enum(StatusValidacao, 20))
    nivel_localizacao: Mapped[NivelLocalizacao] = mapped_column(_enum(NivelLocalizacao, 20))
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    fonte_id: Mapped[int] = mapped_column(ForeignKey("fonte_dados.id"))
    identificador_externo: Mapped[str | None] = mapped_column(String(120))
    nome_relator: Mapped[str | None] = mapped_column(String(120))
    contato_relator: Mapped[str | None] = mapped_column(String(254))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    validado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    data_validacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observacao_validacao: Mapped[str | None] = mapped_column(String(500))
    data_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    fonte: Mapped[FonteDados] = relationship()

    def possui_coordenadas(self) -> bool:
        return self.latitude is not None and self.longitude is not None
