"""Arredondamento e formatação de números com as mesmas regras dos textos do AlertaLar.

O ``round`` do Python arredonda os empates para o par (2,5 → 2). Os textos e medidas do sistema
arredondam os empates para cima (2,5 → 3), como se costuma fazer à mão.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal


def arredondar(valor: float) -> int:
    """Inteiro mais próximo, com empates para cima (2,5 → 3; -2,5 → -2)."""
    if math.isnan(valor):
        return 0
    return math.floor(valor + 0.5)


def casas(valor: float, n: int) -> float:
    """Arredonda para n casas decimais (empates para cima)."""
    fator = 10 ** n
    return arredondar(valor * fator) / fator


def decimal(valor: float, n: int, virgula: bool = False) -> str:
    """Texto com n casas decimais ("%.nf"), empates para cima; vírgula no padrão brasileiro."""
    quantia = Decimal(repr(float(valor))).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)
    texto = f"{quantia:.{n}f}"
    return texto.replace(".", ",") if virgula else texto


def inteiro_br(valor: int) -> str:
    """1234567 → "1.234.567"."""
    return f"{valor:,}".replace(",", ".")
