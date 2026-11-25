"""Cálculo de rotas com o Valhalla (motor de rotas aberto sobre o OpenStreetMap).

Por padrão usa o servidor público da FOSSGIS (valhalla1.openstreetmap.de), cuja política pede
User-Agent identificável, no máximo 1 requisição por segundo e uso moderado. A URL é configurável
(instância própria ou provedor compatível, como Stadia Maps).
Documentação: https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from alertalar.erros import IntegracaoExterna
from alertalar.integracoes import http
from alertalar.integracoes.http import ClienteHttpExterno, LimitadorIntervalo
from alertalar.util import texto as txt

FONTE = "Valhalla (FOSSGIS / OpenStreetMap)"
PRECISAO_POLYLINE = 6


class ModoRota(str, Enum):
    """Modo de deslocamento da rota segura e o perfil ("costing") equivalente no Valhalla."""

    A_PE = "A_PE"
    CARRO = "CARRO"

    @property
    def costing(self) -> str:
        return {"A_PE": "pedestrian", "CARRO": "auto"}[self.value]

    @property
    def rotulo(self) -> str:
        return {"A_PE": "A pé", "CARRO": "De carro"}[self.value]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Instrucao:
    """Uma manobra do trajeto ("Vire à direita na Rua X")."""

    texto: str | None
    distancia_metros: float
    duracao_segundos: float
    indice_ponto: int
    tipo: int


@dataclass(frozen=True)
class Rota:
    """Trajeto calculado: pontos ``(lat, lon)``, instruções em português, distância (m) e duração (s)."""

    pontos: list[tuple[float, float]]
    instrucoes: list[Instrucao]
    distancia_metros: float
    duracao_segundos: float


class ValhallaClient:
    def __init__(self, cliente: ClienteHttpExterno, url_base: str, chave_api: str | None,
                 limitador: LimitadorIntervalo):
        self.http = cliente
        self.url_base = http.sem_barra_final(url_base)
        self.chave_api = chave_api
        self.limitador = limitador

    def rota(self, lat_origem: float, lon_origem: float, lat_destino: float, lon_destino: float, modo: ModoRota,
             evitar: list | None = None) -> Rota:
        """``evitar``: polígonos (anéis de ``(lat, lon)``) cujas vias o roteador deve evitar."""
        corpo = {
            "locations": [{"lat": lat_origem, "lon": lon_origem}, {"lat": lat_destino, "lon": lon_destino}],
            "costing": modo.costing,
            "directions_options": {"units": "kilometers", "language": "pt-BR"},
        }
        if evitar:
            # O Valhalla usa [lon, lat]
            corpo["exclude_polygons"] = [[[p[1], p[0]] for p in anel] for anel in evitar]
        url = self.url_base + "/route" + ("" if txt.vazio(self.chave_api) else "?api_key=" + http.codificar(self.chave_api))
        self.limitador.aguardar_vez()
        return interpretar(self.http.post_json(FONTE, url, corpo))


def interpretar(dados) -> Rota:
    trip = http.campo(dados, "trip")
    pernas = http.campo(trip, "legs")
    if trip is None or not isinstance(pernas, list) or not pernas:
        erro = http.texto(dados, "error")
        raise IntegracaoExterna(FONTE, "O serviço de rotas não encontrou um caminho"
                                + ("." if erro is None else f" ({erro})."))
    pontos: list[tuple[float, float]] = []
    instrucoes: list[Instrucao] = []
    for perna in pernas:
        deslocamento = len(pontos)
        pontos.extend(decodificar(http.texto(perna, "shape"), PRECISAO_POLYLINE))
        for m in http.lista(http.campo(perna, "maneuvers")):
            km = http.numero(m, "length")
            s = http.numero(m, "time")
            indice = http.numero(m, "begin_shape_index")
            tipo = http.campo(m, "type")
            instrucoes.append(Instrucao(
                http.texto(m, "instruction"), 0 if km is None else km * 1000, 0 if s is None else s,
                deslocamento if indice is None else deslocamento + int(indice),
                tipo if isinstance(tipo, int) and not isinstance(tipo, bool) else 0))
    if len(pontos) < 2:
        raise IntegracaoExterna(FONTE, "O serviço de rotas retornou um trajeto vazio.")
    resumo = http.campo(trip, "summary")
    km = http.numero(resumo, "length")
    segundos = http.numero(resumo, "time")
    return Rota(pontos, instrucoes, 0 if km is None else km * 1000, 0 if segundos is None else segundos)


# ------------------------------------------------------------------ polyline codificada

def decodificar(codificado: str | None, precisao: int) -> list[tuple[float, float]]:
    """Decodifica o formato "encoded polyline" do Valhalla (precisão de 6 casas decimais).
    Referência: https://valhalla.github.io/valhalla/decoding/"""
    pontos: list[tuple[float, float]] = []
    if not codificado:
        return pontos
    fator = 10 ** precisao
    indice = lat = lon = 0
    while indice < len(codificado):
        valor, indice = _ler_valor(codificado, indice)
        lat += valor
        if indice >= len(codificado):
            break
        valor, indice = _ler_valor(codificado, indice)
        lon += valor
        pontos.append((lat / fator, lon / fator))
    return pontos


def _ler_valor(s: str, inicio: int) -> tuple[int, int]:
    resultado = deslocamento = 0
    i = inicio
    while True:
        if i >= len(s):
            raise ValueError("Polyline truncada")
        b = ord(s[i]) - 63
        i += 1
        resultado |= (b & 0x1F) << deslocamento
        deslocamento += 5
        if b < 0x20:
            break
    valor = ~(resultado >> 1) if resultado & 1 else resultado >> 1
    return valor, i


def codificar(pontos: list, precisao: int) -> str:
    """Codificação (usada nos testes e para simular respostas do Valhalla)."""
    fator = 10 ** precisao
    partes = []
    lat_anterior = lon_anterior = 0
    for p in pontos:
        lat = _arredondar(p[0] * fator)
        lon = _arredondar(p[1] * fator)
        partes.append(_escrever_valor(lat - lat_anterior))
        partes.append(_escrever_valor(lon - lon_anterior))
        lat_anterior, lon_anterior = lat, lon
    return "".join(partes)


def _arredondar(v: float) -> int:
    return math.floor(v + 0.5)


def _escrever_valor(valor: int) -> str:
    v = ~(valor << 1) if valor < 0 else valor << 1
    saida = []
    while v >= 0x20:
        saida.append(chr((0x20 | (v & 0x1F)) + 63))
        v >>= 5
    saida.append(chr(v + 63))
    return "".join(saida)
