"""Consulta de CEP e localização de endereços para confirmar no mapa."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request

from alertalar.controladores.comum import Parametros, servicos
from alertalar.esquemas import CepResponse, EnderecoRequest, LocalizacaoResponse

rotas = APIRouter(prefix="/api/enderecos", tags=["endereços"])


@rotas.get("/cep/{cep}", response_model=CepResponse)
def cep(cep: str, request: Request):
    """Consulta de CEP (ViaCEP) para preencher o formulário. Ex.: GET /api/enderecos/cep/92010000"""
    Parametros().regra("cep", re.fullmatch(r"\d{5}-?\d{3}", cep, re.ASCII) is not None,
                       "O CEP deve ter 8 dígitos.").conferir()
    return servicos(request).enderecos.buscar_cep(cep)


@rotas.get("/buscar", response_model=LocalizacaoResponse)
def buscar(request: Request, cep: str | None = None, rua: str | None = None, numero: str | None = None,
           bairro: str | None = None, cidade: str | None = None, estado: str | None = None,
           latitude: float | None = None, longitude: float | None = None):
    """Valida e geocodifica um endereço, devolvendo os candidatos para confirmação no mapa.
    Ex.: GET /api/enderecos/buscar?rua=Rua X&numero=100&cidade=Canoas&estado=RS"""
    endereco = EnderecoRequest(cep=cep, rua=rua, numero=numero, bairro=bairro, cidade=cidade, estado=estado,
                               latitude=latitude, longitude=longitude).validar()
    return servicos(request).enderecos.localizar(endereco)
