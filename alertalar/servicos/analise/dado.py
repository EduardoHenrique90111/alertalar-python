"""Valor obtido de uma fonte, ou o motivo pelo qual não pôde ser obtido. Permite que cada fonte
falhe de forma independente sem derrubar a análise."""

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
        """Executa a coleta e converte qualquer falha em "indisponível", com mensagem segura."""
        try:
            return Dado.de(coleta())
        except Exception as e:  # noqa: BLE001 - cada fonte falha sozinha, sem derrubar a análise
            return Dado.indisponivel(str(e) or "Fonte indisponível.")
