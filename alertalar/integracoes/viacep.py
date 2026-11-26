from __future__ import annotations

from dataclasses import dataclass

from alertalar.integracoes import http
from alertalar.integracoes.http import CacheTemporario, ClienteHttpExterno
from alertalar.util import texto as txt

FONTE = "ViaCEP"


@dataclass(frozen=True)
class DadosCep:
    cep: str
    logradouro: str | None
    bairro: str | None
    cidade: str
    uf: str
    codigo_ibge: str | None


class ViaCepClient:
    def __init__(self, cliente: ClienteHttpExterno, url_base: str):
        self.http = cliente
        self.url_base = http.sem_barra_final(url_base)
        self._cache: CacheTemporario[str, tuple[DadosCep | None]] = CacheTemporario(24 * 3600, 5_000)

    def buscar(self, cep: str | None) -> DadosCep | None:
        digitos = txt.somente_digitos(cep)
        if len(digitos) != 8:
            return None
        return self._cache.obter_ou_calcular(digitos, lambda: (self._consultar(digitos),))[0]

    def _consultar(self, digitos: str) -> DadosCep | None:
        dados = self.http.get_json(FONTE, f"{self.url_base}/{digitos}/json/")
        erro = http.texto(dados, "erro")
        if erro is not None and erro.lower() == "true":
            return None
        cidade = http.texto(dados, "localidade")
        uf = http.texto(dados, "uf")
        if cidade is None or uf is None:
            return None
        return DadosCep(txt.formatar_cep(digitos), http.texto(dados, "logradouro"), http.texto(dados, "bairro"),
                        cidade, uf.upper(), http.texto(dados, "ibge"))
