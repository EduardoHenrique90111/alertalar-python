"""Geocodificação com o Photon (komoot), que busca nos mesmos dados do OpenStreetMap que o
Nominatim, em outro servidor. É a reserva quando o Nominatim público recusa pedidos (limite por IP,
comum em hospedagens compartilhadas) ou não responde. Uso justo, sem chave: https://photon.komoot.io
"""

from __future__ import annotations

from alertalar.integracoes import http
from alertalar.integracoes.http import ClienteHttpExterno, LimitadorIntervalo
from alertalar.integracoes.nominatim import ResultadoGeocodificacao
from alertalar.util.uf import UnidadeFederativa

FONTE = "Photon (OpenStreetMap)"

# Retângulo que contém o Brasil (oeste, sul, leste, norte), no formato do Photon
CAIXA_BRASIL = "-74.2,-34.0,-28.6,5.5"


class PhotonClient:
    def __init__(self, cliente: ClienteHttpExterno, url_base: str, limitador: LimitadorIntervalo):
        self.http = cliente
        self.url_base = http.sem_barra_final(url_base)
        self.limitador = limitador

    def buscar(self, consulta: str, limite: int) -> list[ResultadoGeocodificacao]:
        """Busca por texto livre, só no Brasil."""
        p = {"q": consulta, "limit": max(1, min(limite, 15)), "bbox": CAIXA_BRASIL}
        self.limitador.aguardar_vez()
        resposta = self.http.get_json(FONTE, http.uri(self.url_base + "/api", p))
        resultados = []
        for item in http.lista(http.campo(resposta, "features")):
            r = _converter(item)
            if r is not None:
                resultados.append(r)
        return resultados


def _converter(item) -> ResultadoGeocodificacao | None:
    coordenadas = http.campo(http.campo(item, "geometry"), "coordinates")
    p = http.campo(item, "properties")
    pais = http.texto(p, "countrycode")
    if not isinstance(coordenadas, list) or len(coordenadas) < 2 or (pais or "").upper() != "BR":
        return None
    lon = http.numero(coordenadas[0]) or 0.0
    lat = http.numero(coordenadas[1]) or 0.0
    tipo = http.texto(p, "type")
    nome = http.texto(p, "name")
    rua = http.texto(p, "street")
    if rua is None and tipo == "street":
        rua = nome  # o resultado é a própria rua
    cidade = http.texto(p, "city")
    if cidade is None and tipo == "city":
        cidade = nome
    bairro = http.texto(p, "district") or http.texto(p, "locality")
    estado = http.texto(p, "state")
    uf = UnidadeFederativa.de_texto(estado)
    numero = http.texto(p, "housenumber")
    cep = http.texto(p, "postcode")
    nome_lugar = nome if nome is not None and nome != rua else None
    exibicao = _juntar(nome_lugar, numero, rua, bairro, cidade, estado, cep, "Brasil")
    return ResultadoGeocodificacao(lat, lon, rank(tipo), http.texto(p, "osm_value"), numero, rua, bairro, cidade,
                                   uf.name if uf else None, cep, exibicao)


def rank(tipo: str | None) -> int:
    """Equivalente ao place_rank do Nominatim, para a mesma regra de precisão:
    30 = edificação, número ou lugar; 26 = rua; abaixo = bairro, cidade ou região."""
    return {"house": 30, "street": 26, "locality": 20, "district": 20, "city": 16, "county": 12,
            "state": 8, "country": 4}.get(tipo, 18) if tipo is not None else 18


def _juntar(*partes: str | None) -> str:
    """"Canoas Shopping, 6750, Avenida Guilherme Schell, Centro, Canoas, ..." (estilo do Nominatim)."""
    lista: list[str] = []
    for parte in partes:
        if parte and parte.strip() and (not lista or lista[-1] != parte):
            lista.append(parte)
    return ", ".join(lista)
