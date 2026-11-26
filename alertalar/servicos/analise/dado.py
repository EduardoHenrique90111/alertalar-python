from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Dado(Generic[T]):
    valor: T | None
    disponivel: bool
    motivo_indisponibilidade: str | None
    obtido_em: datetime

    @staticmethod
    def de(valor: T) -> Dado[T]:
        return Dado(valor, True, None, datetime.now(timezone.utc))

    @staticmethod
    def indisponivel(motivo: str) -> Dado[T]:
        return Dado(None, False, motivo, datetime.now(timezone.utc))

    @staticmethod
    def coletar(coleta: Callable[[], T]) -> Dado[T]:
        try:
            return Dado.de(coleta())
        except Exception as e:
            return Dado.indisponivel(str(e) or "Fonte indisponível.")
