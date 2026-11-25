"""Exceções da aplicação e respostas de erro no formato Problem Details (RFC 9457).

As mensagens são em português e nunca expõem detalhes internos (pilha de chamadas, SQL,
nomes de classes).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("alertalar.erros")

TIPO_PROBLEMA = "application/problem+json"


class RecursoNaoEncontrado(Exception):
    pass


class EnderecoNaoEncontrado(Exception):
    """O endereço informado não foi localizado pelos serviços de geocodificação ou de CEP."""


class RegraNegocio(Exception):
    """Violação de regra de negócio (ex.: e-mail já cadastrado, transição de status inválida)."""


class ArquivoInvalido(Exception):
    """Arquivo de importação em formato não reconhecido."""


class RequisicaoInvalida(ValueError):
    """Parâmetro ou valor inválido (equivale ao IllegalArgumentException da versão em Java)."""


class PrecisaoInsuficiente(Exception):
    """O endereço foi encontrado apenas no nível de bairro, CEP ou cidade, o que não é preciso o
    bastante para analisar o risco de um imóvel."""

    def __init__(self, mensagem: str, latitude_aproximada: float | None, longitude_aproximada: float | None):
        super().__init__(mensagem)
        self.latitude_aproximada = latitude_aproximada
        self.longitude_aproximada = longitude_aproximada


class IntegracaoExterna(Exception):
    """Falha ao consultar uma fonte externa (indisponibilidade, tempo esgotado, resposta inválida)."""

    def __init__(self, fonte: str, mensagem: str, status_http: int | None = None,
                 espera_pedida: float | None = None):
        super().__init__(mensagem)
        self.fonte = fonte
        # Código HTTP com que a fonte recusou o pedido (ex.: 429, limite atingido), se ela chegou a responder
        self.status_http = status_http
        # Tempo de espera pedido pela fonte no cabeçalho Retry-After (em segundos), se houver
        self.espera_pedida = espera_pedida


class FalhaAutenticacao(Exception):
    """E-mail ou senha incorretos."""


class ContaDesativada(FalhaAutenticacao):
    pass


class AcessoNegado(Exception):
    pass


class DadosInvalidos(Exception):
    """Campos de um formulário com valores inválidos (resposta 400 com a lista "erros")."""

    def __init__(self, erros: dict[str, str], titulo: str = "Dados inválidos",
                 detalhe: str = "Verifique os campos destacados."):
        super().__init__(detalhe)
        self.erros = erros
        self.titulo = titulo
        self.detalhe = detalhe


class ParametrosInvalidos(DadosInvalidos):
    """Parâmetros da URL fora dos limites aceitos."""

    def __init__(self, erros: dict[str, str]):
        super().__init__(erros, "Parâmetros inválidos", "Verifique os parâmetros enviados.")


def problema(status: int, titulo: str, detalhe: str, instancia: str | None = None, **extras: Any) -> dict:
    corpo: dict[str, Any] = {"type": "about:blank", "title": titulo, "status": status, "detail": detalhe}
    if instancia is not None:
        corpo["instance"] = instancia
    corpo.update(extras)
    return corpo


def resposta_problema(status: int, titulo: str, detalhe: str, instancia: str | None = None,
                      cabecalhos: dict[str, str] | None = None, **extras: Any) -> JSONResponse:
    return JSONResponse(problema(status, titulo, detalhe, instancia, **extras), status_code=status,
                        media_type=TIPO_PROBLEMA, headers=cabecalhos)


def titulo_padrao(status: int) -> str:
    return {400: "Requisição inválida", 404: "Não encontrado", 405: "Método não permitido",
            406: "Formato não aceito", 413: "Conteúdo muito grande",
            415: "Tipo de conteúdo não suportado"}.get(status, "Erro interno" if status >= 500 else "Erro na requisição")


def detalhe_padrao(status: int) -> str:
    return {400: "A requisição está malformada ou contém valores inválidos.",
            404: "O recurso solicitado não existe.",
            405: "Este método HTTP não é aceito neste endereço.",
            413: "O arquivo excede o tamanho máximo de 25 MB.",
            415: "Envie os dados no formato JSON."}.get(
        status, "Ocorreu um erro inesperado." if status >= 500 else "Não foi possível processar a requisição.")


def registrar_tratadores(app: FastAPI) -> None:
    """Converte as exceções em respostas Problem Details."""

    def caminho(req: Request) -> str:
        return req.url.path

    @app.exception_handler(DadosInvalidos)
    async def _dados_invalidos(req: Request, ex: DadosInvalidos):
        return resposta_problema(400, ex.titulo, ex.detalhe, caminho(req), erros=ex.erros)

    @app.exception_handler(RequestValidationError)
    async def _validacao(req: Request, ex: RequestValidationError):
        # Corpo malformado, parâmetro obrigatório ausente ou de tipo errado
        return resposta_problema(400, titulo_padrao(400), detalhe_padrao(400), caminho(req))

    @app.exception_handler(StarletteHTTPException)
    async def _http(req: Request, ex: StarletteHTTPException):
        cabecalhos = {"Allow": ex.headers["Allow"]} if ex.headers and "Allow" in ex.headers else None
        return resposta_problema(ex.status_code, titulo_padrao(ex.status_code), detalhe_padrao(ex.status_code),
                                 caminho(req), cabecalhos)

    @app.exception_handler(RecursoNaoEncontrado)
    async def _nao_encontrado(req: Request, ex: RecursoNaoEncontrado):
        return resposta_problema(404, "Não encontrado", str(ex), caminho(req))

    @app.exception_handler(EnderecoNaoEncontrado)
    async def _endereco_nao_encontrado(req: Request, ex: EnderecoNaoEncontrado):
        return resposta_problema(404, "Endereço não encontrado", str(ex), caminho(req))

    @app.exception_handler(PrecisaoInsuficiente)
    async def _precisao(req: Request, ex: PrecisaoInsuficiente):
        return resposta_problema(422, "Precisão insuficiente", str(ex), caminho(req),
                                 codigo="PRECISAO_INSUFICIENTE", latitudeAproximada=ex.latitude_aproximada,
                                 longitudeAproximada=ex.longitude_aproximada)

    @app.exception_handler(RegraNegocio)
    async def _regra(req: Request, ex: RegraNegocio):
        return resposta_problema(422, "Operação não permitida", str(ex), caminho(req))

    @app.exception_handler(ArquivoInvalido)
    async def _arquivo(req: Request, ex: ArquivoInvalido):
        return resposta_problema(400, "Arquivo inválido", str(ex), caminho(req))

    @app.exception_handler(RequisicaoInvalida)
    async def _requisicao(req: Request, ex: RequisicaoInvalida):
        return resposta_problema(400, "Requisição inválida", str(ex) or "Parâmetros inválidos.", caminho(req))

    @app.exception_handler(IntegracaoExterna)
    async def _integracao(req: Request, ex: IntegracaoExterna):
        return resposta_problema(503, "Serviço externo indisponível", str(ex), caminho(req), fonte=ex.fonte)

    @app.exception_handler(ContaDesativada)
    async def _desativada(req: Request, ex: ContaDesativada):
        return resposta_problema(401, "Conta desativada", "Esta conta está desativada.", caminho(req))

    @app.exception_handler(FalhaAutenticacao)
    async def _autenticacao(req: Request, ex: FalhaAutenticacao):
        return resposta_problema(401, "Falha na autenticação", "E-mail ou senha incorretos.", caminho(req))

    @app.exception_handler(AcessoNegado)
    async def _acesso(req: Request, ex: AcessoNegado):
        return resposta_problema(403, "Acesso negado", "Você não tem permissão para esta operação.", caminho(req))


def corpo_erro_inesperado(ex: BaseException, instancia: str) -> dict:
    """Erro não previsto: registra no log com um código curto e devolve só esse código."""
    codigo = uuid.uuid4().hex[:8]
    log.error("Erro inesperado [%s]", codigo, exc_info=ex)
    return problema(500, "Erro interno", "Ocorreu um erro inesperado. Tente novamente em instantes. "
                    "Código para suporte: " + codigo, instancia)
