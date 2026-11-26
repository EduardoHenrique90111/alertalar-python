from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


@dataclass(frozen=True)
class Resposta:
    status: int
    corpo: str
    atraso_s: float = 0.0
    cabecalhos: tuple[tuple[str, str], ...] = ()

    @staticmethod
    def json(corpo: str) -> Resposta:
        return Resposta(200, corpo)

    @staticmethod
    def erro(status: int, cabecalhos: tuple[tuple[str, str], ...] = ()) -> Resposta:
        return Resposta(status, '{"error":true}', 0.0, cabecalhos)


@dataclass(frozen=True)
class Requisicao:
    metodo: str
    caminho: str
    query: str
    corpo: str
    cabecalhos: dict[str, str]

    def cabecalho(self, nome: str) -> str | None:
        return next((v for k, v in self.cabecalhos.items() if k.lower() == nome.lower()), None)

    def parametro(self, nome: str) -> str | None:
        fonte = self.corpo if self.metodo == "POST" and not self.query else self.query
        valores = parse_qs(fonte or "", keep_blank_values=True).get(nome)
        return valores[0] if valores else None


Rota = Callable[[Requisicao], Resposta]


class ServidorHttpFalso:
    def __init__(self) -> None:
        self._rotas: dict[str, Rota] = {}
        self.recebidas: list[Requisicao] = []
        servidor = self

        class Tratador(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:
                pass

            def _tratar(self) -> None:
                partes = urlsplit(self.path)
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(tamanho).decode("utf-8") if tamanho else ""
                req = Requisicao(self.command, partes.path, partes.query, corpo, dict(self.headers.items()))
                servidor.recebidas.append(req)
                candidatas = [p for p in servidor._rotas if partes.path.startswith(p)]
                if candidatas:
                    resp = servidor._rotas[max(candidatas, key=len)](req)
                else:
                    resp = Resposta(404, '{"erro":"rota nao simulada"}')
                if resp.atraso_s > 0:
                    time.sleep(resp.atraso_s)
                dados = resp.corpo.encode("utf-8")
                try:
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(dados)))
                    for nome, valor in resp.cabecalhos:
                        self.send_header(nome, valor)
                    self.end_headers()
                    self.wfile.write(dados)
                except OSError:
                    pass

            do_GET = do_POST = _tratar

        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), Tratador)
        self._servidor.daemon_threads = True
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()

    def rota(self, prefixo: str, resposta: Rota | Resposta) -> ServidorHttpFalso:
        self._rotas[prefixo] = resposta if callable(resposta) else (lambda req, r=resposta: r)
        return self

    def url(self, caminho: str) -> str:
        return f"http://127.0.0.1:{self._servidor.server_address[1]}{caminho}"

    def contar(self, prefixo: str) -> int:
        return sum(1 for r in self.recebidas if r.caminho.startswith(prefixo))

    def fechar(self) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()

    def __enter__(self) -> ServidorHttpFalso:
        return self

    def __exit__(self, *_) -> None:
        self.fechar()
