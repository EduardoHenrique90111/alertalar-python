from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal


def arredondar(valor: float) -> int:
    if math.isnan(valor):
        return 0
    return math.floor(valor + 0.5)


def casas(valor: float, n: int) -> float:
    fator = 10 ** n
    return arredondar(valor * fator) / fator


def decimal(valor: float, n: int, virgula: bool = False) -> str:
    quantia = Decimal(repr(float(valor))).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)
    texto = f"{quantia:.{n}f}"
    return texto.replace(".", ",") if virgula else texto


def inteiro_br(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")
