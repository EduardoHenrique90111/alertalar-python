from __future__ import annotations

from dataclasses import dataclass

from alertalar.integracoes import http
from alertalar.integracoes.http import ClienteHttpExterno

FONTE = "OpenStreetMap (Overpass API)"

PRINCIPAIS = frozenset({"river", "canal", "tidal_channel", "water", "riverbank"})


@dataclass(frozen=True)
class CursoDagua:
    osm_id: int
    tipo: str
    subtipo: str | None
    nome: str | None
    principal: bool
    area: bool
    partes: tuple[tuple[tuple[float, float], ...], ...]

    def descricao(self) -> str:
        rotulos = {"river": "rio", "stream": "córrego/arroio", "canal": "canal", "drain": "canal de drenagem",
                   "ditch": "vala", "tidal_channel": "canal de maré"}
        if self.tipo in rotulos:
            rotulo = rotulos[self.tipo]
        else:
            rotulo = {"river": "rio (margens)", "lake": "lago", "reservoir": "reservatório", "pond": "lagoa/açude",
                      "lagoon": "laguna"}.get(self.subtipo, "corpo d'água") if self.subtipo is not None \
                else "corpo d'água"
        return rotulo if self.nome is None else f"{rotulo} {self.nome}"


class OverpassClient:
    def __init__(self, cliente: ClienteHttpExterno, url: str):
        self.http = cliente
        self.url = url

    def buscar_proximos(self, latitude: float, longitude: float, raio_metros: int) -> list[CursoDagua]:
        around = f"(around:{int(raio_metros)},{latitude:.6f},{longitude:.6f})"
        consulta = ("[out:json][timeout:25];("
                    f'way["waterway"~"^(river|stream|canal|drain|ditch|tidal_channel)$"]{around};'
                    f'way["natural"="water"]{around};'
                    f'relation["natural"="water"]{around};'
                    ");out tags geom qt;")
        return interpretar(self.http.post_formulario_json(FONTE, self.url, {"data": consulta}))


def interpretar(dados) -> list[CursoDagua]:
    cursos = []
    for el in http.lista(http.campo(dados, "elements")):
        tipo_elemento = http.texto(el, "type")
        tags = http.campo(el, "tags")
        waterway = http.texto(tags, "waterway")
        natural = http.texto(tags, "natural")
        tipo = waterway if waterway is not None else ("water" if natural == "water" else None)
        if tipo is None:
            continue
        nome = http.texto(tags, "name")
        subtipo = http.texto(tags, "water")
        osm_id = int(http.numero(el, "id") or 0)
        principal = tipo in PRINCIPAIS or subtipo in ("river", "canal")
        area = tipo_elemento != "way" or waterway is None
        if tipo_elemento == "way":
            pontos = _ler_geometria(http.campo(el, "geometry"))
            if pontos:
                cursos.append(CursoDagua(osm_id, tipo, subtipo, nome, principal, area, (pontos,)))
        elif tipo_elemento == "relation":
            partes = tuple(p for p in (_ler_geometria(http.campo(m, "geometry"))
                                       for m in http.lista(http.campo(el, "members"))) if p)
            if partes:
                cursos.append(CursoDagua(osm_id, tipo, subtipo, nome, principal, True, partes))
    return cursos


def _ler_geometria(geometria) -> tuple[tuple[float, float], ...]:
    pontos = []
    for p in http.lista(geometria):
        lat = http.numero(p, "lat")
        lon = http.numero(p, "lon")
        if lat is not None and lon is not None:
            pontos.append((lat, lon))
    return tuple(pontos)
