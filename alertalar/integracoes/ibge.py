"""Código IBGE (7 dígitos) do município, usado para cruzar o endereço com os registros oficiais.

Duas fontes: a lista guardada no próprio sistema (:class:`MunicipiosIbge`) e a API de Localidades
do IBGE (https://servicodados.ibge.gov.br/api/docs/localidades) para o que não estiver nela.
"""

from __future__ import annotations

import gzip
import logging
import re
from importlib import resources

from alertalar.integracoes import http
from alertalar.integracoes.http import CacheTemporario, ClienteHttpExterno
from alertalar.util import texto as txt

log = logging.getLogger("alertalar.integracoes.ibge")

FONTE = "IBGE - API de Localidades"
RECURSO_MUNICIPIOS = "municipios-ibge.csv.gz"


class IbgeLocalidadesClient:
    def __init__(self, cliente: ClienteHttpExterno, url_base: str):
        self.http = cliente
        self.url_base = http.sem_barra_final(url_base)
        self._cache: CacheTemporario[str, dict[str, str]] = CacheTemporario(24 * 3600, 30)

    def codigo_municipio(self, uf: str | None, nome_municipio: str | None) -> str | None:
        if txt.vazio(uf) or txt.vazio(nome_municipio):
            return None
        sigla = uf.upper()
        municipios = self._cache.obter_ou_calcular(sigla, lambda: self._carregar(sigla))
        return municipios.get(txt.normalizar(nome_municipio))

    def _carregar(self, uf: str) -> dict[str, str]:
        dados = self.http.get_json(FONTE, f"{self.url_base}/estados/{uf}/municipios")
        mapa: dict[str, str] = {}
        if isinstance(dados, list):
            for m in dados:
                codigo = http.texto(m, "id")
                nome = http.texto(m, "nome")
                if codigo is not None and nome is not None:
                    mapa[txt.normalizar(nome)] = codigo
        return mapa


class MunicipiosIbge:
    """Códigos IBGE de município guardados no próprio sistema (sem depender da API do IBGE, que pode
    ficar fora do ar ou não responder a servidores fora do Brasil).

    A lista vem do Atlas Digital de Desastres no Brasil v1.1 (MIDR/Sedec), que traz o código IBGE
    oficial de cada município com algum registro: 5.256 municípios, com as diferentes grafias do
    nome que aparecem nos registros. Para município fora da lista o sistema ainda tenta a API do IBGE.
    """

    def __init__(self, codigos: dict[str, str]):
        self._codigos = dict(codigos)

    @classmethod
    def carregar(cls) -> MunicipiosIbge:
        mapa: dict[str, str] = {}
        try:
            dados = resources.files("alertalar.dados").joinpath(RECURSO_MUNICIPIOS).read_bytes()
        except (FileNotFoundError, ModuleNotFoundError):
            log.warning("Lista local de municípios (%s) não encontrada; o código IBGE dependerá da API do IBGE",
                        RECURSO_MUNICIPIOS)
            return cls(mapa)
        linhas = gzip.decompress(dados).decode("utf-8").splitlines()
        for linha in linhas[1:]:  # a primeira é o cabeçalho
            c = linha.split(";", 2)
            if len(c) == 3 and re.fullmatch(r"\d{7}", c[0]):
                mapa.setdefault(chave(c[1], c[2]), c[0])
        return cls(mapa)

    @classmethod
    def vazio(cls) -> MunicipiosIbge:
        """Lista vazia: força o uso da API do IBGE (útil em testes)."""
        return cls({})

    @classmethod
    def de(cls, linhas: list[tuple[str, str, str]]) -> MunicipiosIbge:
        """Monta a lista a partir de linhas (código, UF, nome)."""
        mapa: dict[str, str] = {}
        for codigo, uf, nome in linhas:
            mapa.setdefault(chave(uf, nome), codigo)
        return cls(mapa)

    def codigo(self, uf: str | None, nome_municipio: str | None) -> str | None:
        if not uf or not nome_municipio or not uf.strip() or not nome_municipio.strip():
            return None
        return self._codigos.get(chave(uf, nome_municipio))

    def tamanho(self) -> int:
        return len(self._codigos)


def chave(uf: str, nome: str) -> str:
    """Simplifica o nome para comparar grafias diferentes: sem acentos, minúsculo e só letras e
    números ("Herval D`Oeste", "Herval d'Oeste" e "HERVAL DOESTE" viram "hervaldoeste")."""
    return uf.strip().upper() + "|" + re.sub(r"[^a-z0-9]", "", txt.sem_acentos(nome).lower())
