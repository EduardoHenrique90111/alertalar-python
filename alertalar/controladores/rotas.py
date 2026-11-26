from __future__ import annotations

import asyncio
import json
import logging
import threading

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from alertalar.controladores.comum import Parametros, servicos
from alertalar.erros import IntegracaoExterna, RegraNegocio, RequisicaoInvalida
from alertalar.esquemas import RotaSeguraResponse
from alertalar.integracoes.valhalla import ModoRota
from alertalar.servicos.progresso_rota import CalculoCancelado, Evento, ProgressoRota

log = logging.getLogger("alertalar.rota")

rotas = APIRouter(prefix="/api/rotas", tags=["rota segura"])

TEMPO_MAXIMO_SEGUNDOS = 180


def _conferir(lat: float, lon: float, dest_lat: float | None, dest_lon: float | None) -> None:
    (Parametros().latitude("lat", lat).longitude("lon", lon).latitude("destLat", dest_lat)
     .longitude("destLon", dest_lon).conferir())
    if dest_lat is None or dest_lon is None:
        raise RequisicaoInvalida("Informe o destino da rota: destLat e destLon.")


@rotas.get("/segura", response_model=RotaSeguraResponse)
def segura(request: Request, lat: float, lon: float, modo: ModoRota = ModoRota.A_PE, destLat: float | None = None,
           destLon: float | None = None):
    _conferir(lat, lon, destLat, destLon)
    return servicos(request).rotas.calcular(lat, lon, destLat, destLon, modo)


class _Envio(ProgressoRota):
    def __init__(self, loop: asyncio.AbstractEventLoop, fila: asyncio.Queue):
        self._loop = loop
        self._fila = fila
        self._desistiu = threading.Event()

    def informar(self, evento: Evento) -> None:
        self.enviar("etapa", evento.como_json())

    def cancelado(self) -> bool:
        return self._desistiu.is_set()

    def desistir(self) -> None:
        self._desistiu.set()

    def enviar(self, nome: str | None, dados) -> None:
        if not self._desistiu.is_set():
            self._loop.call_soon_threadsafe(self._fila.put_nowait, (nome, dados))

    def erro(self, status: int, titulo: str, detalhe: str) -> None:
        self.enviar("erro", {"status": status, "title": titulo, "detail": detalhe})


def _evento(nome: str, dados) -> str:
    return f"event: {nome}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


@rotas.get("/segura/progresso")
async def segura_com_progresso(request: Request, lat: float, lon: float, modo: ModoRota = ModoRota.A_PE,
                               destLat: float | None = None, destLon: float | None = None):
    _conferir(lat, lon, destLat, destLon)
    s = servicos(request)
    s.rotas.validar(lat, lon, destLat, destLon)
    loop = asyncio.get_running_loop()
    fila: asyncio.Queue = asyncio.Queue()
    envio = _Envio(loop, fila)

    def calcular() -> None:
        try:
            r = s.rotas.calcular(lat, lon, destLat, destLon, modo, envio)
            envio.enviar("resultado", r.model_dump(mode="json"))
        except CalculoCancelado:
            log.debug("Rota cancelada por quem pediu.")
        except RegraNegocio as e:
            envio.erro(422, "Operação não permitida", str(e))
        except IntegracaoExterna as e:
            envio.erro(503, "Serviço externo indisponível", str(e))
        except Exception:
            log.exception("Erro inesperado ao calcular a rota segura")
            envio.erro(500, "Erro interno", "Não foi possível calcular a rota agora. Tente novamente em instantes.")
        finally:
            envio.enviar(None, None)

    loop.run_in_executor(s.executor_rotas, calcular)

    async def eventos():
        prazo = loop.time() + TEMPO_MAXIMO_SEGUNDOS
        try:
            while True:
                try:
                    nome, dados = await asyncio.wait_for(fila.get(), timeout=max(0.0, prazo - loop.time()))
                except TimeoutError:
                    yield _evento("erro", {"status": 503, "title": "Cálculo demorado demais",
                                           "detail": "Os serviços de mapas não responderam a tempo. Tente novamente "
                                                     "em instantes."})
                    return
                if nome is None:
                    return
                yield _evento(nome, dados)
        finally:
            envio.desistir()

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
