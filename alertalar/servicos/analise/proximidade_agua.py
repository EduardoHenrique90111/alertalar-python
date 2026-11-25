"""Ponto mais próximo de um curso/corpo d'água em relação ao endereço consultado."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from alertalar.integracoes.overpass import CursoDagua
from alertalar.util import geo


@dataclass(frozen=True)
class ProximidadeAgua:
    curso: CursoDagua
    latitude: float
    longitude: float
    distancia_metros: float


def mais_proximo(lat: float, lon: float, cursos: Iterable[CursoDagua],
                 filtro: Callable[[CursoDagua], bool] = lambda c: True) -> ProximidadeAgua | None:
    melhor: ProximidadeAgua | None = None
    for c in cursos:
        if not filtro(c):
            continue
        for parte in c.partes:
            if c.area and len(parte) >= 4 and geo.dentro_do_poligono(lat, lon, parte):
                return ProximidadeAgua(c, lat, lon, 0)
            p = geo.ponto_mais_proximo(lat, lon, parte)
            if p is not None and (melhor is None or p[2] < melhor.distancia_metros):
                melhor = ProximidadeAgua(c, p[0], p[1], p[2])
    return melhor
