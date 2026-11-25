"""Open-Meteo: elevação do terreno (Copernicus DEM GLO-90), chuva observada/prevista e vazão
modelada de rios (GloFAS). A chuva e a vazão são dados da SITUAÇÃO ATUAL e não entram na
classificação de risco histórico."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from alertalar.erros import IntegracaoExterna
from alertalar.integracoes import http
from alertalar.integracoes.http import ClienteHttpExterno

FONTE_ELEVACAO = "Copernicus DEM GLO-90 (Open-Meteo)"
FONTE_CHUVA = "Open-Meteo (previsão meteorológica)"
FONTE_VAZAO = "GloFAS (Open-Meteo Flood API)"


class ElevacaoClient:
    """Elevação pelo Copernicus DEM GLO-90 (resolução de 90 m), servido pela Open-Meteo Elevation
    API (https://open-meteo.com/en/docs/elevation-api). Aceita até 100 coordenadas por requisição."""

    FONTE = FONTE_ELEVACAO
    MAXIMO_POR_REQUISICAO = 100

    def __init__(self, cliente: ClienteHttpExterno, url: str):
        self.http = cliente
        self.url = url

    def elevacoes(self, pontos: list) -> list[float | None]:
        """Elevações em metros, na mesma ordem dos pontos ``(lat, lon)`` (None quando não houver dado)."""
        if not pontos:
            return []
        if len(pontos) > self.MAXIMO_POR_REQUISICAO:
            raise ValueError(f"Máximo de {self.MAXIMO_POR_REQUISICAO} pontos por requisição")
        p = {"latitude": ",".join(f"{c[0]:.6f}" for c in pontos),
             "longitude": ",".join(f"{c[1]:.6f}" for c in pontos)}
        dados = self.http.get_json(FONTE_ELEVACAO, http.uri(self.url, p))
        if isinstance(dados, dict) and dados.get("error") is True:
            raise IntegracaoExterna(FONTE_ELEVACAO, http.texto(dados, "reason") or "Erro reportado pela API Open-Meteo")
        valores = http.campo(dados, "elevation")
        if not isinstance(valores, list) or len(valores) != len(pontos):
            raise IntegracaoExterna(FONTE_ELEVACAO, "A fonte de elevação retornou uma quantidade inesperada de valores.")
        resultado = []
        for v in valores:
            e = http.numero(v)
            resultado.append(None if e is None or e != e else e)  # e != e: NaN
        return resultado


@dataclass(frozen=True)
class SerieChuva:
    """Série horária de chuva (mm) no horário local do ponto."""

    fuso: timezone
    horas: list[datetime]
    milimetros: list[float | None]


@dataclass(frozen=True)
class SerieVazao:
    """Série diária de vazão (m³/s)."""

    dias: list[date]
    metros_cubicos_por_segundo: list[float | None]


class ClimaClient:
    """Chuva observada/prevista (Open-Meteo Forecast API) e vazão modelada de rios (GloFAS via
    Open-Meteo Flood API)."""

    def __init__(self, cliente: ClienteHttpExterno, url_previsao: str, url_vazao: str):
        self.http = cliente
        self.url_previsao = url_previsao
        self.url_vazao = url_vazao

    def chuva_horaria(self, lat: float, lon: float) -> SerieChuva:
        p = {"latitude": f"{lat:.5f}", "longitude": f"{lon:.5f}", "hourly": "precipitation", "past_days": 3,
             "forecast_days": 4, "timezone": "auto"}
        dados = self.http.get_json(FONTE_CHUVA, http.uri(self.url_previsao, p))
        offset = int(http.numero(dados, "utc_offset_seconds") or 0)
        horaria = http.campo(dados, "hourly")
        tempos = http.lista(http.campo(horaria, "time"))
        chuva = http.lista(http.campo(horaria, "precipitation"))
        n = min(len(tempos), len(chuva))
        return SerieChuva(timezone(timedelta(seconds=offset)), [datetime.fromisoformat(t) for t in tempos[:n]],
                          [http.numero(v) for v in chuva[:n]])

    def vazao_diaria(self, lat: float, lon: float) -> SerieVazao:
        p = {"latitude": f"{lat:.5f}", "longitude": f"{lon:.5f}", "daily": "river_discharge", "past_days": 7,
             "forecast_days": 7}
        dados = self.http.get_json(FONTE_VAZAO, http.uri(self.url_vazao, p))
        diaria = http.campo(dados, "daily")
        tempos = http.lista(http.campo(diaria, "time"))
        vazao = http.lista(http.campo(diaria, "river_discharge"))
        n = min(len(tempos), len(vazao))
        return SerieVazao([date.fromisoformat(t) for t in tempos[:n]], [http.numero(v) for v in vazao[:n]])
