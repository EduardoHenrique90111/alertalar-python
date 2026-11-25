"""Dados reais coletados para um ponto, entregues aos fatores de risco.

Os fatores são funções puras deste contexto, o que facilita testá-los isoladamente.
"""

from __future__ import annotations

from dataclasses import dataclass

from alertalar.integracoes.overpass import CursoDagua
from alertalar.integracoes.sgb import SetorRisco
from alertalar.modelos.entidades import Ocorrencia
from alertalar.servicos.analise.dado import Dado


@dataclass(frozen=True)
class Parametros:
    raio_cursos_agua_metros: int
    raio_ocorrencias_metros: int
    raio_setores_risco_metros: int
    anos_historico: int


@dataclass(frozen=True)
class OcorrenciaProxima:
    """Ocorrência confirmada com a distância (m) até o ponto consultado."""

    ocorrencia: Ocorrencia
    distancia_metros: float


@dataclass(frozen=True)
class HistoricoMunicipal:
    """Registros oficiais municipais. ``base_importada_para_uf`` indica se a base oficial já foi
    importada para a UF; sem isso, "zero registros" não pode ser lido como ausência de eventos."""

    registros: list[Ocorrencia]
    base_importada_para_uf: bool


@dataclass(frozen=True)
class PerfilElevacao:
    """Elevações (m) do Copernicus DEM.

    ``elevacao_ponto``: no ponto consultado; ``elevacao_agua``: no ponto do curso d'água mais próximo
    (pode ser nula); ``distancia_agua_metros``: distância até esse ponto; ``nome_agua``: descrição do
    curso d'água de referência; ``media_entorno``: média num anel ao redor do ponto, de raio
    ``raio_entorno_metros``; ``pontos_entorno``: quantos pontos do anel tinham dado.
    """

    elevacao_ponto: float | None
    elevacao_agua: float | None
    distancia_agua_metros: float | None
    nome_agua: str | None
    media_entorno: float | None
    raio_entorno_metros: int
    pontos_entorno: int


@dataclass(frozen=True)
class ContextoAnalise:
    latitude: float
    longitude: float
    uf: str | None
    codigo_ibge: str | None
    parametros: Parametros
    cursos_dagua: Dado[list[CursoDagua]]
    elevacao: Dado[PerfilElevacao]
    setores_risco: Dado[list[SetorRisco]]
    ocorrencias_proximas: Dado[list[OcorrenciaProxima]]
    historico_municipal: Dado[HistoricoMunicipal]

