from __future__ import annotations

import hashlib
import importlib
import logging
import re
from dataclasses import dataclass
from importlib import resources

from sqlalchemy import Connection, Engine, text

log = logging.getLogger("alertalar.migracoes")

TABELA = "historico_migracoes"
_NOME = re.compile(r"V(\d+)__(\w+)\.(sql|py)")


@dataclass(frozen=True)
class Migracao:
    versao: int
    descricao: str
    arquivo: str
    tipo: str

    def conteudo(self) -> bytes:
        return resources.files(__package__).joinpath(self.arquivo).read_bytes()

    def soma(self) -> str:
        return hashlib.sha256(self.conteudo()).hexdigest()[:16]


def disponiveis() -> list[Migracao]:
    lista = []
    for item in resources.files(__package__).iterdir():
        m = _NOME.fullmatch(item.name)
        if m:
            lista.append(Migracao(int(m.group(1)), m.group(2).replace("_", " "), item.name, m.group(3)))
    versoes = [m.versao for m in lista]
    if len(versoes) != len(set(versoes)):
        raise RuntimeError("Há duas migrações com o mesmo número de versão.")
    return sorted(lista, key=lambda m: m.versao)


def aplicar(engine: Engine) -> list[int]:
    aplicadas_agora = []
    with engine.begin() as conexao:
        conexao.execute(text("SELECT pg_advisory_xact_lock(4627119)"))
        _criar_tabela(conexao)
        ja_aplicadas = _versoes_aplicadas(conexao)
    for migracao in disponiveis():
        if migracao.versao in ja_aplicadas:
            continue
        with engine.begin() as conexao:
            conexao.execute(text("SELECT pg_advisory_xact_lock(4627119)"))
            if migracao.versao in _versoes_aplicadas(conexao):
                continue
            log.info("Aplicando migração V%d (%s)", migracao.versao, migracao.descricao)
            if migracao.tipo == "sql":
                with conexao.connection.cursor() as cursor:
                    cursor.execute(migracao.conteudo().decode("utf-8"))
            else:
                modulo = importlib.import_module(f"{__package__}.{migracao.arquivo[:-3]}")
                modulo.migrar(conexao)
            conexao.execute(text(f"INSERT INTO {TABELA} (versao, descricao, arquivo, soma) "
                                 "VALUES (:v, :d, :a, :s)"),
                            {"v": migracao.versao, "d": migracao.descricao, "a": migracao.arquivo, "s": migracao.soma()})
            aplicadas_agora.append(migracao.versao)
    return aplicadas_agora


def _criar_tabela(conexao: Connection) -> None:
    conexao.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            versao       INTEGER PRIMARY KEY,
            descricao    VARCHAR(200) NOT NULL,
            arquivo      VARCHAR(200) NOT NULL,
            soma         VARCHAR(64),
            aplicada_em  TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""))
    flyway = conexao.execute(text("SELECT to_regclass('flyway_schema_history') IS NOT NULL")).scalar()
    if flyway:
        conexao.execute(text(f"""
            INSERT INTO {TABELA} (versao, descricao, arquivo, soma)
            SELECT CAST(version AS INTEGER), description, script, 'flyway'
              FROM flyway_schema_history
             WHERE success AND version ~ '^[0-9]+$'
            ON CONFLICT (versao) DO NOTHING"""))


def _versoes_aplicadas(conexao: Connection) -> set[int]:
    return set(conexao.execute(text(f"SELECT versao FROM {TABELA}")).scalars())
