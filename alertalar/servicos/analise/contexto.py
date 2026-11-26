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
    ocorrencia: Ocorrencia
    distancia_metros: float


@dataclass(frozen=True)
class HistoricoMunicipal:
    registros: list[Ocorrencia]
    base_importada_para_uf: bool


@dataclass(frozen=True)
class PerfilElevacao:
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
