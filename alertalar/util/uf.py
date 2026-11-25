"""As 27 unidades federativas do Brasil."""

from __future__ import annotations

from enum import Enum

from alertalar.util import texto


class UnidadeFederativa(Enum):
    AC = "Acre"
    AL = "Alagoas"
    AP = "Amapá"
    AM = "Amazonas"
    BA = "Bahia"
    CE = "Ceará"
    DF = "Distrito Federal"
    ES = "Espírito Santo"
    GO = "Goiás"
    MA = "Maranhão"
    MT = "Mato Grosso"
    MS = "Mato Grosso do Sul"
    MG = "Minas Gerais"
    PA = "Pará"
    PB = "Paraíba"
    PR = "Paraná"
    PE = "Pernambuco"
    PI = "Piauí"
    RJ = "Rio de Janeiro"
    RN = "Rio Grande do Norte"
    RS = "Rio Grande do Sul"
    RO = "Rondônia"
    RR = "Roraima"
    SC = "Santa Catarina"
    SP = "São Paulo"
    SE = "Sergipe"
    TO = "Tocantins"

    @property
    def nome(self) -> str:
        return self.value

    @classmethod
    def da_sigla(cls, sigla: str | None) -> UnidadeFederativa | None:
        if sigla is None:
            return None
        return cls.__members__.get(sigla.strip().upper())

    @classmethod
    def de_texto(cls, valor: str | None) -> UnidadeFederativa | None:
        """Aceita sigla ("RS") ou nome ("Rio Grande do Sul", com ou sem acento)."""
        por_sigla = cls.da_sigla(valor)
        if por_sigla is not None:
            return por_sigla
        n = texto.normalizar(valor)
        return next((uf for uf in cls if texto.normalizar(uf.value) == n), None)


SIGLAS = frozenset(UnidadeFederativa.__members__)


def sigla_valida(valor: str | None) -> bool:
    """Mesma regra da validação dos formulários: a sigla exata, em maiúsculas ou minúsculas."""
    return valor is not None and valor.upper() in SIGLAS
