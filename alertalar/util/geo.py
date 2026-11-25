"""Cálculos geográficos simples (sem dependências externas).

Para distâncias de até alguns quilômetros usa-se uma projeção equiretangular local, com erro
desprezível para esta escala. Pontos são pares ``(lat, lon)``; listas de pontos formam linhas.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

RAIO_TERRA_METROS = 6_371_008.8

# Limites aproximados do território brasileiro (inclui ilhas oceânicas)
LAT_MIN_BRASIL = -34.0
LAT_MAX_BRASIL = 5.5
LON_MIN_BRASIL = -74.2
LON_MAX_BRASIL = -28.6

Ponto = Sequence[float]


def dentro_do_brasil(lat: float, lon: float) -> bool:
    return LAT_MIN_BRASIL <= lat <= LAT_MAX_BRASIL and LON_MIN_BRASIL <= lon <= LON_MAX_BRASIL


def distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em metros entre dois pontos (fórmula de Haversine)."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return 2 * RAIO_TERRA_METROS * math.asin(min(1.0, math.sqrt(a)))


def ponto_mais_proximo(lat: float, lon: float, linha: Sequence[Ponto] | None) -> tuple[float, float, float] | None:
    """Ponto da polilinha mais próximo do ponto de referência: ``(lat, lon, distância em metros)``."""
    if not linha:
        return None
    if len(linha) == 1:
        p = linha[0]
        return p[0], p[1], distancia_metros(lat, lon, p[0], p[1])
    cos_lat = math.cos(math.radians(lat))
    melhor_dist = math.inf
    melhor = None
    for a, b in zip(linha, linha[1:]):
        # coordenadas locais em metros, origem no ponto de referência
        ax = math.radians(a[1] - lon) * cos_lat * RAIO_TERRA_METROS
        ay = math.radians(a[0] - lat) * RAIO_TERRA_METROS
        bx = math.radians(b[1] - lon) * cos_lat * RAIO_TERRA_METROS
        by = math.radians(b[0] - lat) * RAIO_TERRA_METROS
        dx, dy = bx - ax, by - ay
        comp2 = dx * dx + dy * dy
        t = 0.0 if comp2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / comp2))
        px, py = ax + t * dx, ay + t * dy
        d = math.hypot(px, py)
        if d < melhor_dist:
            melhor_dist = d
            p_lat = lat + math.degrees(py / RAIO_TERRA_METROS)
            p_lon = lon + math.degrees(px / (RAIO_TERRA_METROS * cos_lat))
            melhor = (p_lat, p_lon, d)
    return melhor


def dentro_do_poligono(lat: float, lon: float, anel: Sequence[Ponto] | None) -> bool:
    """Teste ponto-em-polígono (ray casting). O anel é uma lista de ``(lat, lon)``."""
    if anel is None or len(anel) < 3:
        return False
    dentro = False
    j = len(anel) - 1
    for i in range(len(anel)):
        yi, xi = anel[i][0], anel[i][1]
        yj, xj = anel[j][0], anel[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def deslocar(lat: float, lon: float, distancia_m: float, rumo_graus: float) -> tuple[float, float]:
    """Ponto deslocado a partir de uma origem, dada a distância (m) e o rumo (graus a partir do norte)."""
    d = distancia_m / RAIO_TERRA_METROS
    rumo = math.radians(rumo_graus)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(rumo))
    lon2 = lon1 + math.atan2(math.sin(rumo) * math.sin(d) * math.cos(lat1),
                             math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)


def rumo(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Rumo inicial (graus a partir do norte, 0–360) de um ponto a outro."""
    f1 = math.radians(lat1)
    f2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(f2)
    x = math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


_DIRECOES = ("norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste")


def direcao(rumo_graus: float) -> str:
    """"norte", "nordeste", "leste"... para um rumo em graus."""
    angulo = ((rumo_graus % 360) + 360) % 360
    return _DIRECOES[math.floor(angulo / 45.0 + 0.5) % 8]


def comprimento(linha: Sequence[Ponto]) -> float:
    """Comprimento (m) de uma linha de pontos."""
    return sum(distancia_metros(a[0], a[1], b[0], b[1]) for a, b in zip(linha, linha[1:]))


def amostrar(linha: Sequence[Ponto] | None, quantidade: int) -> list[tuple[float, float, float]]:
    """Pontos igualmente espaçados ao longo da linha (inclui o primeiro e o último).

    Devolve ``(lat, lon, distância desde o início)``.
    """
    if not linha:
        return []
    total = comprimento(linha)
    if quantidade < 2 or total == 0:
        return [(linha[0][0], linha[0][1], 0.0)]
    passo = total / (quantidade - 1)
    resultado = []
    acumulado = 0.0
    i = 1
    for k in range(quantidade):
        alvo = min(k * passo, total)
        while i < len(linha) - 1:
            seg = distancia_metros(linha[i - 1][0], linha[i - 1][1], linha[i][0], linha[i][1])
            if acumulado + seg >= alvo:
                break
            acumulado += seg
            i += 1
        a, b = linha[i - 1], linha[i]
        seg = distancia_metros(a[0], a[1], b[0], b[1])
        t = 0.0 if seg == 0 else max(0.0, min(1.0, (alvo - acumulado) / seg))
        resultado.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), alvo))
    return resultado


def retangulo_envolvente(lat: float, lon: float, raio_metros: float) -> tuple[float, float, float, float]:
    """Retângulo ``(lat_min, lat_max, lon_min, lon_max)`` que envolve um círculo de raio em metros."""
    d_lat = math.degrees(raio_metros / RAIO_TERRA_METROS)
    d_lon = math.degrees(raio_metros / (RAIO_TERRA_METROS * math.cos(math.radians(lat))))
    return lat - d_lat, lat + d_lat, lon - d_lon, lon + d_lon
