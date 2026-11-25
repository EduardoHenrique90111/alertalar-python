"""Fontes de dados, com a situação real de cada integração e a data da última atualização."""

from __future__ import annotations

from fastapi import APIRouter, Request

from alertalar.controladores.comum import servicos
from alertalar.esquemas import FonteResponse
from alertalar.servicos import conversores

rotas = APIRouter(prefix="/api/fontes", tags=["fontes"])


@rotas.get("", response_model=list[FonteResponse])
def listar(request: Request):
    return [conversores.fonte(f) for f in servicos(request).fontes.listar()]
