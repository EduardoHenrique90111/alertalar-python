"""Criação da aplicação web (FastAPI): rotas da API, site estático, segurança e inicialização."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from alertalar import container, migracoes
from alertalar.config import Configuracoes
from alertalar.controladores import admin, auth, consultas, enderecos, fontes, ocorrencias, rotas, situacao_atual
from alertalar.erros import registrar_tratadores
from alertalar.seguranca import ArmazemSessoes, LimitadorRequisicoes, MiddlewareSeguranca

log = logging.getLogger("alertalar")


def localizar_frontend(config: Configuracoes) -> Path | None:
    """Pasta do site: ALERTALAR_FRONTEND, ./frontend, ../frontend ou a que acompanha o código."""
    candidatas = [config.pasta_frontend, Path("frontend"), Path("../frontend"),
                  Path(__file__).resolve().parent.parent / "frontend"]
    for pasta in candidatas:
        if pasta is not None and (pasta / "index.html").is_file():
            return pasta.resolve()
    return None


def criar_app(config: Configuracoes | None = None, servicos: container.Servicos | None = None,
              limitador: LimitadorRequisicoes | None = None) -> FastAPI:
    config = config or (servicos.config if servicos else Configuracoes.do_ambiente())

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        s = app.state.servicos
        if config.aplicar_migracoes:
            try:
                aplicadas = migracoes.aplicar(s.engine)
            except OperationalError as e:
                motivo = str(e.orig if e.orig is not None else e).strip().splitlines()[0]
                log.error("Não foi possível conectar ao banco de dados %s (origem: %s): %s",
                          config.descricao_banco, config.origem_banco, motivo)
                raise
            if aplicadas:
                log.info("Migrações aplicadas: %s", ", ".join(f"V{v}" for v in aplicadas))
        container.criar_admin_inicial(s)
        yield
        if servicos is None:  # quem recebeu os serviços prontos (ex.: testes) cuida de encerrá-los
            s.encerrar()

    app = FastAPI(title="AlertaLar", version="1.0",
                  description="Consulta de riscos de enchentes e alagamentos a partir de dados públicos.",
                  lifespan=ciclo_de_vida, openapi_url="/api/openapi.json",
                  # Sem a página interativa (/docs): ela carrega scripts de uma CDN, o que a política de
                  # segurança de conteúdo do site não permite. A descrição da API fica em /api/openapi.json.
                  docs_url=None, redoc_url=None)
    app.state.servicos = servicos or container.montar(config)
    registrar_tratadores(app)

    for modulo in (auth, consultas, enderecos, fontes, ocorrencias, rotas, situacao_atual, admin):
        app.include_router(modulo.rotas)

    @app.get("/actuator/health", include_in_schema=False)
    def saude():
        try:
            with app.state.servicos.engine.connect() as conexao:
                conexao.execute(text("SELECT 1"))
            return {"status": "UP"}
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "DOWN"}, status_code=503)

    pasta = localizar_frontend(config)
    if pasta is not None:
        app.mount("/", StaticFiles(directory=pasta, html=True), name="site")
    else:
        log.warning("Pasta do front-end não encontrada: só a API estará disponível.")

    app.add_middleware(MiddlewareSeguranca, config=config, armazem=ArmazemSessoes(),
                       limitador=limitador or LimitadorRequisicoes())
    if config.confiar_proxy:
        # Atrás de proxy reverso (Render, Nginx...): IP e protocolo reais vêm de X-Forwarded-*
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    return app
