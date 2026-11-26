from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from alertalar.controladores.comum import Parametros, ler_corpo, servicos, usuario_obrigatorio
from alertalar.erros import ArquivoInvalido
from alertalar.esquemas import ImportacaoResultado, OcorrenciaAdminResponse, PaginaResponse, ValidacaoRequest
from alertalar.modelos.enums import StatusValidacao

rotas = APIRouter(prefix="/api/admin", tags=["moderação"])

TAMANHO_MAXIMO_ARQUIVO = 25 * 1024 * 1024


@rotas.get("/resumo")
def resumo(request: Request) -> dict:
    return {"relatosPendentes": servicos(request).ocorrencias.contar_pendentes()}


@rotas.get("/ocorrencias", response_model=PaginaResponse[OcorrenciaAdminResponse])
def listar(request: Request, status: StatusValidacao = StatusValidacao.PENDENTE, busca: str | None = None,
           pagina: int = 0, tamanho: int = 20):
    (Parametros().tamanho_maximo("busca", busca, 100).faixa("pagina", pagina, "0").faixa("tamanho", tamanho, "1", "100")
     .conferir())
    return servicos(request).ocorrencias.listar_para_moderacao(status, busca, pagina, tamanho)


@rotas.patch("/ocorrencias/{id_ocorrencia}/validacao", response_model=OcorrenciaAdminResponse)
async def validar(id_ocorrencia: int, request: Request):
    req = (await ler_corpo(request, ValidacaoRequest)).validar()
    moderador = await usuario_obrigatorio(request)
    return await run_in_threadpool(servicos(request).ocorrencias.validar, id_ocorrencia, req, moderador)


@rotas.post("/importacoes/registros-oficiais", response_model=ImportacaoResultado)
async def importar(request: Request):
    if int(request.headers.get("content-length") or 0) > TAMANHO_MAXIMO_ARQUIVO + 64 * 1024:
        raise HTTPException(413)
    if "multipart/form-data" not in request.headers.get("content-type", ""):
        raise HTTPException(415)
    formulario = await request.form(max_files=1, max_fields=10)
    arquivo = formulario.get("arquivo")
    if not isinstance(arquivo, UploadFile):
        raise HTTPException(400)
    conteudo = await arquivo.read(TAMANHO_MAXIMO_ARQUIVO + 1)
    if len(conteudo) > TAMANHO_MAXIMO_ARQUIVO:
        raise HTTPException(413)
    if not conteudo:
        raise ArquivoInvalido("Selecione um arquivo CSV.")
    nome = arquivo.filename or "planilha.csv"
    if not nome.lower().endswith((".csv", ".txt")):
        raise ArquivoInvalido("Envie a planilha no formato CSV (no Excel: Arquivo > Salvar como > CSV UTF-8).")
    administrador = await usuario_obrigatorio(request)
    return await run_in_threadpool(servicos(request).importacao.importar_registros_oficiais, conteudo, nome,
                                   administrador)
