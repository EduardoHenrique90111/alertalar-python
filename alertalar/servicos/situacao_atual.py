from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from alertalar.erros import RegraNegocio
from alertalar.esquemas import Chuva, SituacaoAtualResponse, Vazao
from alertalar.integracoes.http import CacheTemporario
from alertalar.integracoes.open_meteo import FONTE_CHUVA, FONTE_VAZAO, ClimaClient, SerieChuva, SerieVazao
from alertalar.repositorios import ConsultaRepositorio
from alertalar.servicos.analise import risco_agora
from alertalar.servicos.analise.dado import Dado
from alertalar.servicos.analise.fatores import FatorProximidadeAgua
from alertalar.servicos.fontes import FonteDadosService
from alertalar.util import geo
from alertalar.util.numeros import casas

OBSERVACAO_VAZAO = ("Vazão diária simulada pelo GloFAS numa grade de ~5 km. Representa o rio principal mais "
                    "próximo da grade e pode não refletir córregos ou rios pequenos.")


@dataclass(frozen=True)
class Medidas:
    chuva: Chuva
    vazao: Vazao
    consultado_em: datetime


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class SituacaoAtualService:
    def __init__(self, clima: ClimaClient, fontes: FonteDadosService, consultas: ConsultaRepositorio,
                 relogio: Callable[[], datetime] = _agora):
        self.clima = clima
        self.fontes = fontes
        self.consultas = consultas
        self._relogio = relogio
        self._cache: CacheTemporario[str, Medidas] = CacheTemporario(15 * 60, 2_000)

    def consultar(self, lat: float, lon: float, id_consulta: uuid.UUID | None = None) -> SituacaoAtualResponse:
        if not geo.dentro_do_brasil(lat, lon):
            raise RegraNegocio("As coordenadas informadas estão fora do território brasileiro.")
        chave = f"{lat:.2f},{lon:.2f}"
        m = self._cache.obter_ou_calcular(chave, lambda: self.medir(lat, lon))

        suscetibilidade = None
        perto_de_agua = False
        consulta = None if id_consulta is None else self.consultas.com_fatores(id_consulta)
        if consulta is not None:
            suscetibilidade = consulta.classificacao
            perto_de_agua = any(f.codigo == FatorProximidadeAgua.CODIGO and f.pontuacao is not None and f.pontuacao >= 2
                                for f in consulta.fatores)
        risco = risco_agora.avaliar(m.chuva, m.vazao, suscetibilidade, perto_de_agua)
        return SituacaoAtualResponse(latitude=lat, longitude=lon, risco_agora=risco, chuva=m.chuva, vazao=m.vazao,
                                     avisos=_avisos(), consultado_em=m.consultado_em)

    def medir(self, lat: float, lon: float) -> Medidas:
        chuva = Dado.coletar(lambda: self.clima.chuva_horaria(lat, lon))
        vazao = Dado.coletar(lambda: self.clima.vazao_diaria(lat, lon))
        if chuva.disponivel:
            self.fontes.registrar_acesso("OPEN_METEO_PREVISAO", chuva.obtido_em)
        if vazao.disponivel:
            self.fontes.registrar_acesso("OPEN_METEO_GLOFAS", vazao.obtido_em)
        return Medidas(self.resumir_chuva(chuva), self.resumir_vazao(vazao), self._relogio())

    def resumir_chuva(self, dado: Dado[SerieChuva]) -> Chuva:
        if not dado.disponivel:
            return Chuva.indisponivel(dado.motivo_indisponibilidade, FONTE_CHUVA)
        s = dado.valor
        agora = self._relogio().astimezone(s.fuso).replace(tzinfo=None)
        passado24 = passado72 = max_hora_passada = 0.0
        futuro24 = futuro72 = max_hora_futura = dia2 = dia3 = 0.0
        algum = False
        for h, mm in zip(s.horas, s.milimetros):
            if mm is None:
                continue
            algum = True
            if h <= agora:
                if h > agora - timedelta(hours=72):
                    passado72 += mm
                if h > agora - timedelta(hours=24):
                    passado24 += mm
                    max_hora_passada = max(max_hora_passada, mm)
            elif h <= agora + timedelta(hours=24):
                futuro24 += mm
                futuro72 += mm
                max_hora_futura = max(max_hora_futura, mm)
            elif h <= agora + timedelta(hours=48):
                dia2 += mm
                futuro72 += mm
            elif h <= agora + timedelta(hours=72):
                dia3 += mm
                futuro72 += mm
        if not algum:
            return Chuva.indisponivel("A fonte não retornou dados de chuva para este ponto.", FONTE_CHUVA)
        return Chuva(disponivel=True, motivo=None, ultimas_24h_mm=_arred(passado24), ultimas_72h_mm=_arred(passado72),
                     maior_intensidade_horaria_ultimas_24h_mm=_arred(max_hora_passada),
                     proximas_24h_mm=_arred(futuro24), proximas_72h_mm=_arred(futuro72),
                     maior_intensidade_horaria_proximas_24h_mm=_arred(max_hora_futura),
                     maior_24h_entre_24e72h_mm=_arred(max(dia2, dia3)), fonte=FONTE_CHUVA)

    def resumir_vazao(self, dado: Dado[SerieVazao]) -> Vazao:
        if not dado.disponivel:
            return Vazao(disponivel=False, motivo=dado.motivo_indisponibilidade, hoje_m3s=None,
                         sete_dias_atras_m3s=None, maxima_prevista_7_dias_m3s=None, tendencia=None, fonte=FONTE_VAZAO,
                         observacao=OBSERVACAO_VAZAO)
        s = dado.valor
        hoje: date = self._relogio().astimezone(timezone.utc).date()
        valor_hoje = sete_dias = max_prev = None
        for d, v in zip(s.dias, s.metros_cubicos_por_segundo):
            if v is None:
                continue
            if d == hoje:
                valor_hoje = v
            if d == hoje - timedelta(days=7):
                sete_dias = v
            if d > hoje:
                max_prev = v if max_prev is None else max(max_prev, v)
        sem_dados = all(v is None for v in s.metros_cubicos_por_segundo)
        if sem_dados or valor_hoje is None:
            return Vazao(disponivel=False, motivo="Não há rio modelado pelo GloFAS para este ponto.", hoje_m3s=None,
                         sete_dias_atras_m3s=None, maxima_prevista_7_dias_m3s=None, tendencia=None, fonte=FONTE_VAZAO,
                         observacao=OBSERVACAO_VAZAO)
        tendencia = None
        if max_prev is not None:
            variacao = (max_prev - valor_hoje) / max(valor_hoje, 0.001)
            tendencia = "SUBINDO" if variacao > 0.2 else "DESCENDO" if variacao < -0.2 else "ESTAVEL"
        return Vazao(disponivel=True, motivo=None, hoje_m3s=_arred(valor_hoje),
                     sete_dias_atras_m3s=None if sete_dias is None else _arred(sete_dias),
                     maxima_prevista_7_dias_m3s=None if max_prev is None else _arred(max_prev), tendencia=tendencia,
                     fonte=FONTE_VAZAO, observacao=OBSERVACAO_VAZAO)


def _avisos() -> list[str]:
    return ["Dados de modelos meteorológicos e hidrológicos: não substituem os alertas oficiais.",
            "Para receber alertas oficiais da Defesa Civil por SMS, envie o seu CEP para 40199.",
            "Em emergência ligue 199 (Defesa Civil) ou 193 (Corpo de Bombeiros)."]


def _arred(v: float) -> float:
    return casas(v, 1)
