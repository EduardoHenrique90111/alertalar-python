from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from alertalar.controladores.comum import Parametros, servicos
from alertalar.esquemas import SituacaoAtualResponse

rotas = APIRouter(prefix="/api/situacao-atual", tags=["situação atual"])


@rotas.get("", response_model=SituacaoAtualResponse)
def consultar(request: Request, lat: float, lon: float, consulta: uuid.UUID | None = None):
    Parametros().latitude("lat", lat).longitude("lon", lon).conferir()
    return servicos(request).situacao_atual.consultar(lat, lon, consulta)
