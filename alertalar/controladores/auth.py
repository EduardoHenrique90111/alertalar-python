from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from alertalar.controladores.comum import ler_corpo, seguranca, servicos, usuario_atual
from alertalar.esquemas import LoginRequest, RegistroRequest, UsuarioResponse
from alertalar.seguranca import CABECALHO_CSRF
from alertalar.servicos import conversores

rotas = APIRouter(prefix="/api/auth", tags=["autenticação"])


@rotas.get("/csrf")
def csrf() -> dict:
    return {"headerName": CABECALHO_CSRF, "parameterName": "_csrf"}


@rotas.post("/registro", status_code=201, response_model=UsuarioResponse)
async def registrar(request: Request):
    req = (await ler_corpo(request, RegistroRequest)).validar()
    s = servicos(request)
    usuario = await run_in_threadpool(s.usuarios.registrar, req)
    usuario = await run_in_threadpool(s.usuarios.autenticar, usuario.email, req.senha)
    seguranca(request).autenticar(usuario.email, usuario.papel.value)
    return JSONResponse(conversores.usuario(usuario).model_dump(mode="json"), status_code=201)


@rotas.post("/login", response_model=UsuarioResponse)
async def login(request: Request):
    req = (await ler_corpo(request, LoginRequest)).validar()
    usuario = await run_in_threadpool(servicos(request).usuarios.autenticar, req.email.strip(), req.senha)
    seguranca(request).autenticar(usuario.email, usuario.papel.value)
    return conversores.usuario(usuario)


@rotas.get("/me", response_model=UsuarioResponse, responses={204: {"description": "Ninguém entrou"}})
async def me(request: Request):
    usuario = await usuario_atual(request)
    if usuario is None:
        return Response(status_code=204)
    return conversores.usuario(usuario)
