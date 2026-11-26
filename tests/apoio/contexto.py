from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date

from alertalar.integracoes.overpass import CursoDagua
from alertalar.integracoes.sgb import SetorRisco
from alertalar.modelos.entidades import FonteDados, Ocorrencia
from alertalar.modelos.enums import (
    NivelLocalizacao,
    OrigemOcorrencia,
    StatusIntegracao,
    StatusValidacao,
    TipoEvento,
    TipoFonte,
)
from alertalar.servicos.analise.contexto import (
    ContextoAnalise,
    HistoricoMunicipal,
    OcorrenciaProxima,
    Parametros,
    PerfilElevacao,
)
from alertalar.servicos.analise.dado import Dado

LAT = -29.92
LON = -51.18


def ocorrencia(origem: OrigemOcorrencia, nivel: NivelLocalizacao, data: date) -> Ocorrencia:
    return Ocorrencia(origem=origem, nivel_localizacao=nivel, status_validacao=StatusValidacao.CONFIRMADA,
                      tipo_evento=TipoEvento.ALAGAMENTO, data_ocorrencia=data, localizacao="Local de teste",
                      descricao="Ocorrência de teste",
                      fonte=FonteDados(codigo="TESTE", nome="Fonte de teste", tipo=TipoFonte.RELATO_USUARIO,
                                       status_integracao=StatusIntegracao.ATIVA))


class ContextoTeste:
    def __init__(self) -> None:
        self.cursos: Dado = Dado.indisponivel("não consultado")
        self.perfil: Dado = Dado.indisponivel("não consultado")
        self.setores: Dado = Dado.indisponivel("não consultado")
        self.ocorrencias_dado: Dado = Dado.de([])
        self.historico: Dado = Dado.de(HistoricoMunicipal([], False))
        self.codigo_ibge: str | None = "4304606"

    @staticmethod
    def novo() -> ContextoTeste:
        return ContextoTeste()

    def rio_a(self, metros: float) -> ContextoTeste:
        d_lon = metros / (111_320 * math.cos(math.radians(LAT)))
        linha = ((LAT - 0.01, LON + d_lon), (LAT + 0.01, LON + d_lon))
        self.cursos = Dado.de([CursoDagua(1, "river", None, "Rio Teste", True, False, (linha,))])
        return self

    def corrego_a(self, metros: float) -> ContextoTeste:
        d_lat = metros / 111_320
        linha = ((LAT + d_lat, LON - 0.01), (LAT + d_lat, LON + 0.01))
        lista = list(self.cursos.valor) if self.cursos.disponivel else []
        lista.append(CursoDagua(2, "stream", None, "Arroio Teste", False, False, (linha,)))
        self.cursos = Dado.de(lista)
        return self

    def sem_cursos_dagua(self) -> ContextoTeste:
        self.cursos = Dado.de([])
        return self

    def elevacao(self, ponto, agua, distancia_agua, media_entorno) -> ContextoTeste:
        self.perfil = Dado.de(PerfilElevacao(ponto, agua, distancia_agua, "rio Teste", media_entorno, 300, 8))
        return self

    def sem_setores(self) -> ContextoTeste:
        self.setores = Dado.de([])
        return self

    def setor(self, grau: str, deslocamento_graus: float, hidrologico: bool) -> ContextoTeste:
        c = LON + deslocamento_graus
        d = 0.001
        anel = ((LAT - d, c - d), (LAT - d, c + d), (LAT + d, c + d), (LAT + d, c - d), (LAT - d, c - d))
        self.setores = Dado.de([SetorRisco("Canoas", "RS", "RS_01", "Bairro", "Inundação" if hidrologico
                                           else "Deslizamento", grau, "descrição", date(2024, 1, 1), hidrologico,
                                           (anel,))])
        return self

    def ocorrencias(self, quantidade: int, distancia: float) -> ContextoTeste:
        self.ocorrencias_dado = Dado.de([OcorrenciaProxima(ocorrencia(OrigemOcorrencia.RELATO_USUARIO,
                                                                      NivelLocalizacao.PONTO, date(2024, 5, 1)),
                                                           distancia) for _ in range(quantidade)])
        return self

    def historico_municipal(self, registros: int, base_importada: bool) -> ContextoTeste:
        lista = [ocorrencia(OrigemOcorrencia.OFICIAL, NivelLocalizacao.MUNICIPIO, date(2024 - i, 5, 1))
                 for i in range(registros)]
        self.historico = Dado.de(HistoricoMunicipal(lista, base_importada))
        return self

    def sem_codigo_ibge(self) -> ContextoTeste:
        self.codigo_ibge = None
        return self

    def construir(self, ajuste_historico: Callable[[list[Ocorrencia]], None] | None = None) -> ContextoAnalise:
        if ajuste_historico is not None and self.historico.disponivel:
            ajuste_historico(self.historico.valor.registros)
        return ContextoAnalise(LAT, LON, "RS", self.codigo_ibge, Parametros(1500, 500, 300, 30), self.cursos,
                               self.perfil, self.setores, self.ocorrencias_dado, self.historico)
