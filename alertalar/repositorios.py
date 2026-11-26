from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from alertalar.banco import FabricaSessoes
from alertalar.modelos.entidades import Consulta, Endereco, FatorConsulta, FonteDados, Ocorrencia, Usuario
from alertalar.modelos.enums import NivelLocalizacao, OrigemOcorrencia, StatusValidacao

T = TypeVar("T")


@dataclass(frozen=True)
class Pagina(Generic[T]):
    itens: list[T]
    pagina: int
    tamanho: int
    total: int

    @property
    def total_paginas(self) -> int:
        return 0 if self.tamanho == 0 else math.ceil(self.total / self.tamanho)


class ErroIntegridade(Exception):
    pass


class _Repositorio:
    def __init__(self, sessoes: FabricaSessoes):
        self._sessoes = sessoes

    def _salvar(self, objeto, *relacoes):
        try:
            with self._sessoes.begin() as s:
                gravado = s.merge(objeto)
                s.flush()
                for relacao in relacoes:
                    getattr(gravado, relacao)
                return gravado
        except IntegrityError as e:
            raise ErroIntegridade(str(e.orig)) from e


class FonteDadosRepositorio(_Repositorio):
    def por_codigo(self, codigo: str) -> FonteDados | None:
        with self._sessoes() as s:
            return s.scalar(select(FonteDados).where(FonteDados.codigo == codigo))

    def todas_por_id(self) -> list[FonteDados]:
        with self._sessoes() as s:
            return list(s.scalars(select(FonteDados).order_by(FonteDados.id)))

    def salvar(self, fonte: FonteDados) -> FonteDados:
        return self._salvar(fonte)


class UsuarioRepositorio(_Repositorio):
    def por_email(self, email: str) -> Usuario | None:
        with self._sessoes() as s:
            return s.scalar(select(Usuario).where(func.lower(Usuario.email) == email.lower()))

    def existe_email(self, email: str) -> bool:
        with self._sessoes() as s:
            return bool(s.scalar(select(exists().where(func.lower(Usuario.email) == email.lower()))))

    def salvar(self, usuario: Usuario) -> Usuario:
        return self._salvar(usuario)


class EnderecoRepositorio(_Repositorio):
    def por_chave(self, chave: str) -> Endereco | None:
        with self._sessoes() as s:
            return s.scalar(select(Endereco).where(Endereco.chave_normalizada == chave))

    def salvar(self, endereco: Endereco) -> Endereco:
        return self._salvar(endereco)


class ConsultaRepositorio(_Repositorio):
    def salvar(self, consulta: Consulta) -> Consulta:
        return self._salvar(consulta)

    def com_endereco_e_fatores(self, id_consulta: uuid.UUID) -> Consulta | None:
        with self._sessoes() as s:
            return s.scalar(select(Consulta).where(Consulta.id == id_consulta).options(
                joinedload(Consulta.endereco),
                selectinload(Consulta.fatores).joinedload(FatorConsulta.fonte)))

    def com_fatores(self, id_consulta: uuid.UUID) -> Consulta | None:
        with self._sessoes() as s:
            return s.scalar(select(Consulta).where(Consulta.id == id_consulta).options(
                selectinload(Consulta.fatores)))

    def do_usuario(self, usuario_id: int, limite: int = 50) -> list[Consulta]:
        with self._sessoes() as s:
            return list(s.scalars(select(Consulta).where(Consulta.usuario_id == usuario_id)
                                  .options(joinedload(Consulta.endereco))
                                  .order_by(Consulta.data_consulta.desc()).limit(limite)))


class OcorrenciaRepositorio(_Repositorio):
    def salvar(self, ocorrencia: Ocorrencia) -> Ocorrencia:
        return self._salvar(ocorrencia, "fonte")

    def salvar_todas(self, ocorrencias: list[Ocorrencia]) -> None:
        if not ocorrencias:
            return
        try:
            with self._sessoes.begin() as s:
                s.add_all(ocorrencias)
        except IntegrityError as e:
            raise ErroIntegridade(str(e.orig)) from e

    def por_id(self, id_ocorrencia: int) -> Ocorrencia | None:
        with self._sessoes() as s:
            return s.scalar(select(Ocorrencia).where(Ocorrencia.id == id_ocorrencia)
                            .options(joinedload(Ocorrencia.fonte)))

    def buscar_na_area(self, status: StatusValidacao, lat_min: float, lat_max: float, lon_min: float,
                       lon_max: float, desde: date) -> list[Ocorrencia]:
        with self._sessoes() as s:
            return list(s.scalars(
                select(Ocorrencia).options(joinedload(Ocorrencia.fonte))
                .where(Ocorrencia.status_validacao == status,
                       Ocorrencia.latitude.between(lat_min, lat_max),
                       Ocorrencia.longitude.between(lon_min, lon_max),
                       Ocorrencia.data_ocorrencia >= desde)
                .order_by(Ocorrencia.data_ocorrencia.desc())))

    def registros_municipais(self, codigo_ibge: str, status: StatusValidacao, desde: date) -> list[Ocorrencia]:
        with self._sessoes() as s:
            return list(s.scalars(
                select(Ocorrencia).options(joinedload(Ocorrencia.fonte))
                .where(Ocorrencia.codigo_ibge == codigo_ibge,
                       Ocorrencia.nivel_localizacao == NivelLocalizacao.MUNICIPIO,
                       Ocorrencia.status_validacao == status,
                       Ocorrencia.data_ocorrencia >= desde)
                .order_by(Ocorrencia.data_ocorrencia.desc())))

    def existe_base_oficial(self, estado: str) -> bool:
        with self._sessoes() as s:
            return bool(s.scalar(select(exists().where(
                Ocorrencia.estado == estado, Ocorrencia.origem == OrigemOcorrencia.OFICIAL,
                Ocorrencia.nivel_localizacao == NivelLocalizacao.MUNICIPIO))))

    def existe_identificador(self, fonte_id: int, identificador: str) -> bool:
        with self._sessoes() as s:
            return bool(s.scalar(select(exists().where(
                Ocorrencia.fonte_id == fonte_id, Ocorrencia.identificador_externo == identificador))))

    def listar_confirmadas(self, estado: str | None, municipio_minusculo: str | None,
                           origem: OrigemOcorrencia | None, pagina: int, tamanho: int) -> Pagina[Ocorrencia]:
        filtros = [Ocorrencia.status_validacao == StatusValidacao.CONFIRMADA]
        if estado is not None:
            filtros.append(Ocorrencia.estado == estado)
        if municipio_minusculo is not None:
            filtros.append(func.lower(Ocorrencia.municipio) == municipio_minusculo)
        if origem is not None:
            filtros.append(Ocorrencia.origem == origem)
        return self._pagina(filtros, (Ocorrencia.data_ocorrencia.desc(), Ocorrencia.id.asc()), pagina, tamanho)

    def listar_relatos_para_moderacao(self, status: StatusValidacao, busca_like: str | None, pagina: int,
                                      tamanho: int) -> Pagina[Ocorrencia]:
        filtros = [Ocorrencia.origem == OrigemOcorrencia.RELATO_USUARIO, Ocorrencia.status_validacao == status]
        if busca_like is not None:
            filtros.append(or_(*(func.lower(func.coalesce(coluna, "")).like(busca_like, escape="!") for coluna in (
                Ocorrencia.localizacao, Ocorrencia.municipio, Ocorrencia.descricao, Ocorrencia.nome_relator,
                Ocorrencia.contato_relator))))
        return self._pagina(filtros, (Ocorrencia.data_registro.desc(), Ocorrencia.id.desc()), pagina, tamanho)

    def contar_por_status(self, status: StatusValidacao) -> int:
        with self._sessoes() as s:
            return s.scalar(select(func.count()).select_from(Ocorrencia)
                            .where(Ocorrencia.status_validacao == status)) or 0

    def _pagina(self, filtros: list, ordem: tuple, pagina: int, tamanho: int) -> Pagina[Ocorrencia]:
        with self._sessoes() as s:
            total = s.scalar(select(func.count()).select_from(Ocorrencia).where(*filtros)) or 0
            itens = list(s.scalars(select(Ocorrencia).options(joinedload(Ocorrencia.fonte)).where(*filtros)
                                   .order_by(*ordem).offset(pagina * tamanho).limit(tamanho)))
            return Pagina(itens, pagina, tamanho, total)
