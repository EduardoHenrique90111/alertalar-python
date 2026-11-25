"""Banco PostgreSQL dos testes de ponta a ponta.

Os testes de ponta a ponta usam um PostgreSQL de verdade e só rodam quando ALERTALAR_TEST_DB_URL
aponta para um banco EXCLUSIVO PARA TESTES (os dados dele são apagados). Exemplo:

    ALERTALAR_TEST_DB_URL=postgresql://localhost:5432/alertalar_test
    ALERTALAR_TEST_DB_USERNAME=alertalar
    ALERTALAR_TEST_DB_PASSWORD=troque_esta_senha
"""

from __future__ import annotations

import os

import pytest

from alertalar.config import montar_url_sqlalchemy


def url_banco_teste() -> str | None:
    url = os.environ.get("ALERTALAR_TEST_DB_URL", "").strip()
    if not url:
        return None
    return montar_url_sqlalchemy(url, os.environ.get("ALERTALAR_TEST_DB_USERNAME") or "alertalar",
                                 os.environ.get("ALERTALAR_TEST_DB_PASSWORD") or "")


precisa_banco = pytest.mark.skipif(url_banco_teste() is None,
                                   reason="defina ALERTALAR_TEST_DB_URL para os testes com PostgreSQL")
