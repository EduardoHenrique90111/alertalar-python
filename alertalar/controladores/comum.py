from __future__ import annotations

import json
from typing import TypeVar

from fastapi import Request
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from alertalar.container import Servicos
from alertalar.erros import AcessoNegado, ParametrosInvalidos
from alertalar.modelos.entidades import Usuario
from alertalar.seguranca import CHAVE_ESCOPO, ContextoSeguranca

M = TypeVar("M", bound=BaseModel)


def servicos(request: Request) -> Servicos:
    return request.app.state.servicos


def seguranca(request: Request) -> ContextoSeguranca:
    return request.scope[CHAVE_ESCOPO]


async def usuario_atual(request: Request) -> Usuario | None:
    email = seguranca(request).email
    if email is None:
        return None
    return await run_in_threadpool(servicos(request).usuarios.por_email, email)


async def usuario_obrigatorio(request: Request) -> Usuario:
    usuario = await usuario_atual(request)
    if usuario is None:
        raise AcessoNegado("Não autenticado")
    return usuario


async def ler_corpo(request: Request, modelo: type[M]) -> M:
    tipo = request.headers.get("content-type", "")
    if "json" not in tipo.lower():
        raise HTTPException(415)
    try:
        dados = json.loads(await request.body() or b"null")
        if not isinstance(dados, dict):
            raise HTTPException(400)
        return modelo.model_validate(dados)
    except (ValueError, ValidationError) as e:
        raise HTTPException(400) from e


class Parametros:
    def __init__(self) -> None:
        self.erros: dict[str, str] = {}

    def faixa(self, nome: str, valor: float | int | None, minimo: str | None = None,
              maximo: str | None = None) -> Parametros:
        if valor is None or nome in self.erros:
            return self
        if minimo is not None and valor < float(minimo):
            self.erros[nome] = f"deve ser maior que ou igual a {minimo}"
        elif maximo is not None and valor > float(maximo):
            self.erros[nome] = f"deve ser menor que ou igual a {maximo}"
        return self

    def latitude(self, nome: str, valor: float | None) -> Parametros:
        return self.faixa(nome, valor, "-34.0", "5.5")

    def longitude(self, nome: str, valor: float | None) -> Parametros:
        return self.faixa(nome, valor, "-74.2", "-28.6")

    def tamanho_maximo(self, nome: str, valor: str | None, maximo: int) -> Parametros:
        if valor is not None and len(valor) > maximo and nome not in self.erros:
            self.erros[nome] = f"o tamanho deve ser entre 0 e {maximo}"
        return self

    def regra(self, nome: str, ok: bool, mensagem: str) -> Parametros:
        if not ok and nome not in self.erros:
            self.erros[nome] = mensagem
        return self

    def conferir(self) -> None:
        if self.erros:
            raise ParametrosInvalidos(self.erros)
