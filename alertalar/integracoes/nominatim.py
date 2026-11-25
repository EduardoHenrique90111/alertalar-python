"""Geocodificação com o Nominatim (OpenStreetMap).

Respeita a política de uso do serviço público: User-Agent identificável, no máximo 1 requisição
por segundo e cache dos resultados (o cache persistente fica na tabela endereco).
Política: https://operations.osmfoundation.org/policies/nominatim/
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from alertalar.integracoes import http
from alertalar.integracoes.http import ClienteHttpExterno, LimitadorIntervalo
from alertalar.util import texto as txt
from alertalar.util.uf import UnidadeFederativa

FONTE = "Nominatim (OpenStreetMap)"


@dataclass(frozen=True)
class ResultadoGeocodificacao:
    """Resultado de geocodificação. ``place_rank``: 30 = edificação/número; 26-27 = rua;
    16-25 = bairro/localidade; abaixo disso = cidade ou região."""

    latitude: float
    longitude: float
    place_rank: int
    tipo_endereco: str | None
    numero: str | None
    rua: str | None
    bairro: str | None
    cidade: str | None
    uf: str | None
    cep: str | None
    nome_exibicao: str | None

    def com_rank(self, rank: int) -> ResultadoGeocodificacao:
        return replace(self, place_rank=rank)


class NominatimClient:
    def __init__(self, cliente: ClienteHttpExterno, url_base: str, email_contato: str | None,
                 limitador: LimitadorIntervalo):
        self.http = cliente
        self.url_base = http.sem_barra_final(url_base)
        self.email_contato = email_contato
        self.limitador = limitador

    def buscar_estruturado(self, rua: str, numero: str | None, cidade: str, uf: str | None,
                           limite: int) -> list[ResultadoGeocodificacao]:
        """Busca estruturada (mais precisa que texto livre)."""
        p = self._parametros_base(limite)
        p["street"] = rua if txt.vazio(numero) else numero.strip() + " " + rua.strip()
        p["city"] = cidade
        estado = UnidadeFederativa.da_sigla(uf)
        if estado is not None:
            p["state"] = estado.nome
        p["country"] = "Brasil"
        return self._executar(p)

    def buscar_texto(self, consulta: str, limite: int) -> list[ResultadoGeocodificacao]:
        """Busca por texto livre (usada como segunda tentativa)."""
        p = self._parametros_base(limite)
        p["q"] = consulta
        return self._executar(p)

    def _parametros_base(self, limite: int) -> dict:
        p = {"format": "jsonv2", "addressdetails": 1, "countrycodes": "br", "limit": max(1, min(limite, 10)),
             "accept-language": "pt-BR"}
        if not txt.vazio(self.email_contato):
            p["email"] = self.email_contato
        return p

    def _executar(self, parametros: dict) -> list[ResultadoGeocodificacao]:
        self.limitador.aguardar_vez()
        resposta = self.http.get_json(FONTE, http.uri(self.url_base + "/search", parametros))
        resultados: list[ResultadoGeocodificacao] = []
        if not isinstance(resposta, list):
            return resultados
        for item in resposta:
            lat = http.numero(item, "lat")
            lon = http.numero(item, "lon")
            if lat is None or lon is None:
                continue
            end = http.campo(item, "address")
            rank = http.numero(item, "place_rank")
            bairro = _primeiro(end, "suburb", "neighbourhood", "quarter", "city_district", "borough")
            cidade = _primeiro(end, "city", "town", "village", "municipality", "hamlet")
            iso = http.texto(end, "ISO3166-2-lvl4")
            uf = iso[3:] if iso is not None and iso.startswith("BR-") else None
            if uf is None:
                estado = UnidadeFederativa.de_texto(http.texto(end, "state"))
                uf = estado.name if estado else None
            resultados.append(ResultadoGeocodificacao(
                lat, lon, 0 if rank is None else int(rank), http.texto(item, "addresstype"),
                http.texto(end, "house_number"), _primeiro(end, "road", "pedestrian", "footway", "residential"),
                bairro, cidade, uf, http.texto(end, "postcode"), http.texto(item, "display_name")))
        return resultados


def _primeiro(no, *campos: str) -> str | None:
    for c in campos:
        v = http.texto(no, c)
        if v is not None:
            return v
    return None
