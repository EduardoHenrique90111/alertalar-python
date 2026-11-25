"""Coleta, de forma independente e em paralelo, os dados reais de cada fonte para um ponto.
A falha de uma fonte vira "indisponível" naquele fator, sem interromper as demais."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from alertalar.config import Analise
from alertalar.integracoes.http import CacheTemporario
from alertalar.integracoes.open_meteo import ElevacaoClient
from alertalar.integracoes.overpass import CursoDagua, OverpassClient
from alertalar.integracoes.sgb import SetorRisco, SgbSetoresRiscoClient
from alertalar.modelos.entidades import Endereco
from alertalar.modelos.enums import StatusValidacao
from alertalar.repositorios import OcorrenciaRepositorio
from alertalar.servicos.analise import proximidade_agua
from alertalar.servicos.analise.contexto import (
    ContextoAnalise,
    HistoricoMunicipal,
    OcorrenciaProxima,
    Parametros,
    PerfilElevacao,
)
from alertalar.servicos.analise.dado import Dado
from alertalar.servicos.fontes import FonteDadosService
from alertalar.util import geo
from alertalar.util import texto as txt

RAIO_ENTORNO_METROS = 300


def _anos_atras(anos: int, hoje: date | None = None) -> date:
    hoje = hoje or date.today()
    try:
        return hoje.replace(year=hoje.year - anos)
    except ValueError:  # 29 de fevereiro
        return hoje.replace(year=hoje.year - anos, day=28)


class ColetaDadosService:
    def __init__(self, overpass: OverpassClient, elevacao: ElevacaoClient, sgb: SgbSetoresRiscoClient,
                 ocorrencias: OcorrenciaRepositorio, fontes: FonteDadosService, parametros: Analise):
        self.overpass = overpass
        self.elevacao = elevacao
        self.sgb = sgb
        self.ocorrencias = ocorrencias
        self.fontes = fontes
        self.parametros = parametros
        self._executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="coleta")
        # Cache por coordenada (~1 m) para não repetir consultas às APIs públicas em sequência
        self._cache_cursos: CacheTemporario[str, list[CursoDagua]] = CacheTemporario(6 * 3600, 2_000)
        self._cache_setores: CacheTemporario[str, list[SetorRisco]] = CacheTemporario(6 * 3600, 2_000)
        self._cache_elevacao: CacheTemporario[str, PerfilElevacao] = CacheTemporario(7 * 24 * 3600, 5_000)

    def encerrar(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def coletar(self, endereco: Endereco) -> ContextoAnalise:
        lat, lon = endereco.latitude, endereco.longitude
        chave = f"{lat:.5f},{lon:.5f}"
        p = self.parametros

        def cursos() -> Dado[list[CursoDagua]]:
            return Dado.coletar(lambda: self._cache_cursos.obter_ou_calcular(
                chave, lambda: self.overpass.buscar_proximos(lat, lon, p.raio_cursos_agua_metros)))

        def setores() -> Dado[list[SetorRisco]]:
            return Dado.coletar(lambda: self._cache_setores.obter_ou_calcular(
                chave, lambda: self.sgb.buscar_proximos(lat, lon, p.raio_setores_risco_metros)))

        # A elevação depende do curso d'água mais próximo (ponto de referência do desnível), então
        # roda logo depois dos cursos d'água, na mesma tarefa. Só guarda em cache quando os cursos
        # estavam disponíveis, para não fixar um perfil incompleto.
        def cursos_e_elevacao() -> tuple[Dado[list[CursoDagua]], Dado[PerfilElevacao]]:
            dado_cursos = cursos()
            if dado_cursos.disponivel:
                return dado_cursos, Dado.coletar(lambda: self._cache_elevacao.obter_ou_calcular(
                    chave, lambda: self.perfil_elevacao(lat, lon, dado_cursos)))
            return dado_cursos, Dado.coletar(lambda: self.perfil_elevacao(lat, lon, dado_cursos))

        futuro_cursos = self._executor.submit(cursos_e_elevacao)
        futuro_setores = self._executor.submit(setores)

        proximas = Dado.coletar(lambda: self.ocorrencias_proximas(lat, lon))
        historico = Dado.coletar(lambda: self.historico_municipal(endereco.estado, endereco.codigo_ibge))

        dado_cursos, perfil = futuro_cursos.result()
        dado_setores = futuro_setores.result()

        if dado_cursos.disponivel:
            self.fontes.registrar_acesso("OSM_CURSOS_AGUA", dado_cursos.obtido_em)
        if dado_setores.disponivel:
            self.fontes.registrar_acesso("SGB_SETORES_RISCO", dado_setores.obtido_em)
        if perfil.disponivel:
            self.fontes.registrar_acesso("COPERNICUS_DEM", perfil.obtido_em)

        return ContextoAnalise(lat, lon, endereco.estado, endereco.codigo_ibge,
                               Parametros(p.raio_cursos_agua_metros, p.raio_ocorrencias_metros,
                                          p.raio_setores_risco_metros, p.anos_historico),
                               dado_cursos, perfil, dado_setores, proximas, historico)

    def perfil_elevacao(self, lat: float, lon: float, cursos: Dado[list[CursoDagua]]) -> PerfilElevacao:
        """Elevação no ponto, no curso d'água mais próximo e em 8 pontos ao redor (uma única requisição)."""
        pontos = [(lat, lon)] + [geo.deslocar(lat, lon, RAIO_ENTORNO_METROS, i * 45.0) for i in range(8)]
        agua = None
        if cursos.disponivel:
            agua = (proximidade_agua.mais_proximo(lat, lon, cursos.valor, lambda c: c.principal)
                    or proximidade_agua.mais_proximo(lat, lon, cursos.valor))
        if agua is not None:
            pontos.append((agua.latitude, agua.longitude))
        valores = self.elevacao.elevacoes(pontos)
        no_ponto = valores[0]
        anel = [v for v in valores[1:9] if v is not None]
        media = sum(anel) / len(anel) if anel else None
        na_agua = valores[9] if agua is not None else None
        return PerfilElevacao(no_ponto, na_agua, agua.distancia_metros if agua else None,
                              agua.curso.descricao() if agua else None, media, RAIO_ENTORNO_METROS, len(anel))

    def ocorrencias_proximas(self, lat: float, lon: float) -> list[OcorrenciaProxima]:
        """Ocorrências CONFIRMADAS com coordenadas dentro do raio (relatos pendentes ficam de fora)."""
        return self.ocorrencias_no_raio(lat, lon, self.parametros.raio_ocorrencias_metros,
                                        self.parametros.anos_historico)

    def ocorrencias_no_raio(self, lat: float, lon: float, raio: int, anos: int) -> list[OcorrenciaProxima]:
        lat_min, lat_max, lon_min, lon_max = geo.retangulo_envolvente(lat, lon, raio)
        encontradas = self.ocorrencias.buscar_na_area(StatusValidacao.CONFIRMADA, lat_min, lat_max, lon_min, lon_max,
                                                      _anos_atras(anos))
        proximas = [OcorrenciaProxima(o, geo.distancia_metros(lat, lon, o.latitude, o.longitude)) for o in encontradas]
        return sorted((o for o in proximas if o.distancia_metros <= raio), key=lambda o: o.distancia_metros)

    def historico_municipal(self, uf: str | None, codigo_ibge: str | None) -> HistoricoMunicipal:
        if txt.vazio(codigo_ibge):
            return HistoricoMunicipal([], False)
        cobertura = self.ocorrencias.existe_base_oficial(uf)
        registros = self.ocorrencias.registros_municipais(codigo_ibge, StatusValidacao.CONFIRMADA,
                                                          _anos_atras(self.parametros.anos_historico))
        return HistoricoMunicipal(registros, cobertura)
