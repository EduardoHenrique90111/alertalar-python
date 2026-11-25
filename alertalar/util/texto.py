"""Utilitários de texto: normalização para comparação e limpeza de entradas do usuário."""

from __future__ import annotations

import re
import unicodedata

_ESPACOS = re.compile(r"[ \t\n\x0b\f\r]+")
# Caracteres de controle (exceto quebra de linha e tabulação) não são aceitos em textos livres
_CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_ESPACO_OU_TAB = re.compile(r"[ \t]+")
_NAO_DIGITO = re.compile(r"[^0-9]")


def aparar(valor: str) -> str:
    """Remove do início e do fim os espaços e caracteres de controle (código até 32)."""
    inicio, fim = 0, len(valor)
    while inicio < fim and ord(valor[inicio]) <= 32:
        inicio += 1
    while fim > inicio and ord(valor[fim - 1]) <= 32:
        fim -= 1
    return valor[inicio:fim]


def sem_acentos(valor: str) -> str:
    decomposto = unicodedata.normalize("NFD", valor)
    return "".join(c for c in decomposto if not unicodedata.category(c).startswith("M"))


def normalizar(valor: str | None) -> str:
    """"São José  do Norte" → "sao jose do norte". Usado para comparar nomes de cidades e ruas."""
    if valor is None:
        return ""
    return _ESPACOS.sub(" ", aparar(sem_acentos(valor).lower()))


def limpar(valor: str | None) -> str | None:
    """Remove espaços extras e caracteres de controle; devolve None para texto vazio."""
    if valor is None:
        return None
    limpo = aparar(_CONTROLE.sub("", valor))
    limpo = _ESPACO_OU_TAB.sub(" ", limpo)
    return limpo or None


def somente_digitos(valor: str | None) -> str:
    return "" if valor is None else _NAO_DIGITO.sub("", valor)


def formatar_cep(valor: str | None) -> str | None:
    """"93010000" → "93010-000"."""
    d = somente_digitos(valor)
    if len(d) != 8:
        return None
    return d[:5] + "-" + d[5:]


def vazio(valor: str | None) -> bool:
    return valor is None or valor.strip() == ""
