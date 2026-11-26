from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from alertalar.controladores.comum import Parametros, ler_corpo, servicos, usuario_atual
from alertalar.esquemas import OcorrenciaRequest, OcorrenciaResponse, PaginaResponse
from alertalar.modelos.enums import OrigemOcorrencia

rotas = APIRouter(prefix="/api/ocorrencias", tags=["ocorrências"])


@rotas.get("", response_model=PaginaResponse[OcorrenciaResponse])
def listar(request: Request, estado: str | None = None, municipio: str | None = None,
           origem: OrigemOcorrencia | None = None, pagina: int = 0, tamanho: int = 20):
    (Parametros()
     .regra("estado", estado is None or re.fullmatch(r"[A-Za-z]{2}", estado) is not None, "UF inválida")
     .tamanho_maximo("municipio", municipio, 120)
     .faixa("pagina", pagina, "0")
     .faixa("tamanho", tamanho, "1", "100")
     .conferir())
    return servicos(request).ocorrencias.listar_confirmadas(estado, municipio, origem, pagina, tamanho)


@rotas.get("/proximas", response_model=list[OcorrenciaResponse])
def proximas(request: Request, lat: float, lon: float, raio: int = 1000, anos: int = 30):
    (Parametros().latitude("lat", lat).longitude("lon", lon).faixa("raio", raio, "50", "10000")
     .faixa("anos", anos, "1", "100").conferir())
    return servicos(request).ocorrencias.confirmadas_proximas(lat, lon, raio, anos)


@rotas.post("", status_code=201, response_model=OcorrenciaResponse)
async def registrar(request: Request):
    req = (await ler_corpo(request, OcorrenciaRequest)).validar()
    usuario = await usuario_atual(request)
    criada = await run_in_threadpool(servicos(request).ocorrencias.registrar_relato, req, usuario)
    return JSONResponse(criada.model_dump(mode="json"), status_code=201)
