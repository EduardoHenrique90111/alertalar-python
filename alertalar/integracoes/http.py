from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
from urllib.parse import quote_plus

import requests

from alertalar.erros import IntegracaoExterna

log = logging.getLogger("alertalar.integracoes")

K = TypeVar("K")
V = TypeVar("V")


def codificar(valor: Any) -> str:
    return quote_plus("" if valor is None else str(valor), safe="")


def uri(base: str, parametros: Mapping[str, Any] | None = None) -> str:
    if not parametros:
        return base
    query = "&".join(f"{codificar(k)}={codificar(v)}" for k, v in parametros.items() if v is not None)
    return base + ("&" if "?" in base else "?") + query


def sem_barra_final(url: str) -> str:
    return url[:-1] if url.endswith("/") else url


class ClienteHttpExterno:
    def __init__(self, user_agent: str, timeout_conexao: float = 5.0, timeout_leitura: float = 25.0):
        self.user_agent = user_agent
        self.timeout = (timeout_conexao, timeout_leitura)
        self._local = threading.local()

    def _sessao(self) -> requests.Session:
        sessao = getattr(self._local, "sessao", None)
        if sessao is None:
            sessao = requests.Session()
            sessao.headers.update({"User-Agent": self.user_agent, "Accept-Language": "pt-BR,pt;q=0.9"})
            self._local.sessao = sessao
        return sessao

    def get_json(self, fonte: str, url: str) -> Any:
        return self._executar(fonte, "GET", url, headers={"Accept": "application/json"})

    def post_formulario_json(self, fonte: str, url: str, campos: Mapping[str, str]) -> Any:
        corpo = "&".join(f"{codificar(k)}={codificar(v)}" for k, v in campos.items())
        return self._executar(fonte, "POST", url, data=corpo.encode("utf-8"), headers={
            "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})

    def post_json(self, fonte: str, url: str, corpo_json: Any) -> Any:
        corpo = json.dumps(corpo_json, ensure_ascii=False).encode("utf-8")
        return self._executar(fonte, "POST", url, data=corpo, headers={
            "Accept": "application/json", "Content-Type": "application/json"})

    def _executar(self, fonte: str, metodo: str, url: str, **opcoes) -> Any:
        try:
            resposta = self._sessao().request(metodo, url, timeout=self.timeout, allow_redirects=True, **opcoes)
        except (requests.Timeout, requests.ConnectionError) as e:
            log.warning("Fonte %s inacessível: %s", fonte, e)
            raise IntegracaoExterna(fonte, f"A fonte {fonte} não respondeu a tempo ou está inacessível.") from e
        except requests.RequestException as e:
            log.warning("Falha ao consultar %s: %s", fonte, e)
            raise IntegracaoExterna(fonte, f"Falha ao consultar a fonte {fonte}.") from e
        if resposta.status_code >= 400:
            status = resposta.status_code
            log.warning("Fonte %s respondeu HTTP %s", fonte, status)
            detalhe = "limite de requisições da fonte atingido" if status == 429 else f"HTTP {status}"
            raise IntegracaoExterna(fonte, f"A fonte {fonte} não atendeu a solicitação ({detalhe}).",
                                    status_http=status, espera_pedida=_retry_after(resposta.headers.get("Retry-After")))
        return self._ler_json(fonte, resposta.content.decode(resposta.encoding or "utf-8", errors="replace"))

    @staticmethod
    def _ler_json(fonte: str, corpo: str | None) -> Any:
        if corpo is None or not corpo.strip():
            raise IntegracaoExterna(fonte, f"A fonte {fonte} retornou uma resposta vazia.")
        try:
            return json.loads(corpo)
        except ValueError as e:
            log.warning("Resposta não-JSON recebida de %s", fonte)
            raise IntegracaoExterna(fonte, f"A fonte {fonte} retornou dados em formato inesperado.") from e


def _retry_after(valor: str | None) -> float | None:
    if valor is None or not re.fullmatch(r"\d{1,6}", valor.strip()):
        return None
    return float(valor.strip())


def campo(no: Any, nome: str) -> Any:
    return no.get(nome) if isinstance(no, dict) else None


def lista(no: Any) -> list:
    if isinstance(no, list):
        return no
    if isinstance(no, dict):
        return list(no.values())
    return []


def texto(no: Any, nome: str) -> str | None:
    valor = campo(no, nome)
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor.strip() or None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    return None


def numero(valor: Any, nome: str | None = None) -> float | None:
    if nome is not None:
        valor = campo(valor, nome)
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        try:
            return float(valor.strip().replace(",", "."))
        except ValueError:
            return None
    return None


@dataclass
class _Entrada(Generic[V]):
    valor: V
    expira_em: float
    criado_em: float


class CacheTemporario(Generic[K, V]):
    def __init__(self, ttl_segundos: float, tamanho_maximo: int, relogio: Callable[[], float] = time.time):
        self.ttl = ttl_segundos
        self.tamanho_maximo = tamanho_maximo
        self._relogio = relogio
        self._mapa: dict[K, _Entrada[V]] = {}
        self._trava = threading.Lock()

    def obter(self, chave: K) -> V | None:
        with self._trava:
            e = self._mapa.get(chave)
            if e is None:
                return None
            if e.expira_em < self._relogio():
                del self._mapa[chave]
                return None
            return e.valor

    def guardar(self, chave: K, valor: V | None) -> None:
        if valor is None:
            return
        with self._trava:
            agora = self._relogio()
            if len(self._mapa) >= self.tamanho_maximo:
                self._remover_expirados_ou_mais_antigo(agora)
            self._mapa[chave] = _Entrada(valor, agora + self.ttl, agora)

    def obter_ou_calcular(self, chave: K, calculo: Callable[[], V]) -> V:
        existente = self.obter(chave)
        if existente is not None:
            return existente
        valor = calculo()
        self.guardar(chave, valor)
        return valor

    def tamanho(self) -> int:
        return len(self._mapa)

    def _remover_expirados_ou_mais_antigo(self, agora: float) -> None:
        for chave in [k for k, e in self._mapa.items() if e.expira_em < agora]:
            del self._mapa[chave]
        if len(self._mapa) >= self.tamanho_maximo:
            mais_antigo = min(self._mapa.items(), key=lambda item: item[1].criado_em)[0]
            del self._mapa[mais_antigo]


class LimitadorIntervalo:
    def __init__(self, intervalo_segundos: float):
        self.intervalo = intervalo_segundos
        self._ultima: float | None = None
        self._trava = threading.Lock()

    def aguardar_vez(self) -> None:
        with self._trava:
            agora = time.monotonic()
            if self._ultima is not None:
                espera = self._ultima + self.intervalo - agora
                if espera > 0:
                    time.sleep(espera)
            self._ultima = time.monotonic()
