"""Consultas de risco por endereço."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from alertalar.controladores.comum import ler_corpo, servicos, usuario_atual, usuario_obrigatorio
from alertalar.esquemas import ConsultaResponse, ConsultaResumo, EnderecoRequest

rotas = APIRouter(prefix="/api/consultas", tags=["consultas"])


@rotas.post("", status_code=201, response_model=ConsultaResponse)
async def consultar(request: Request):
    """Realiza a consulta de risco para um endereço e grava o resultado."""
    endereco = (await ler_corpo(request, EnderecoRequest)).validar()
    usuario = await usuario_atual(request)
    s = servicos(request)
    id_consulta = await run_in_threadpool(s.consultas.realizar, endereco, usuario)
    resposta = await run_in_threadpool(s.consultas.buscar, id_consulta)
    return JSONResponse(resposta.model_dump(mode="json"), status_code=201,
                        headers={"Location": f"/api/consultas/{id_consulta}"})


@rotas.get("/minhas", response_model=list[ConsultaResumo])
async def minhas(request: Request):
    """Histórico de consultas do usuário logado."""
    usuario = await usuario_obrigatorio(request)
    return await run_in_threadpool(servicos(request).consultas.do_usuario, usuario.id)


@rotas.get("/{id_consulta}", response_model=ConsultaResponse)
def buscar(id_consulta: uuid.UUID, request: Request):
    return servicos(request).consultas.buscar(id_consulta)
