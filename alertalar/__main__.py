"""Inicia o AlertaLar: ``python -m alertalar``.

A porta vem da variável ``PORT`` (padrão 8080) e as demais configurações do ambiente ou do
arquivo ``.env`` (veja ``.env.example``). Roda um único processo: as sessões e o limitador de
requisições ficam em memória.
"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

from alertalar.aplicacao import criar_app
from alertalar.config import ConfiguracaoInvalida, Configuracoes

log = logging.getLogger("alertalar")


def main() -> None:
    logging.basicConfig(level=(os.environ.get("ALERTALAR_LOG") or "INFO").upper(),
                        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s")
    try:
        config = Configuracoes.do_ambiente()
    except ConfiguracaoInvalida as e:
        log.error("Configuração inválida: %s", e)
        sys.exit(2)
    log.info("Banco de dados: %s (origem: %s)", config.descricao_banco, config.origem_banco)
    # proxy_headers=False: quando FORWARD_HEADERS_STRATEGY=framework, a própria aplicação lê os
    # cabeçalhos X-Forwarded-* (veja aplicacao.py); sem isso, eles são ignorados.
    uvicorn.run(criar_app(config), host=os.environ.get("ALERTALAR_HOST") or "0.0.0.0", port=config.porta,
                proxy_headers=False, server_header=False, access_log=False, log_config=None,
                timeout_graceful_shutdown=10)


if __name__ == "__main__":
    main()
