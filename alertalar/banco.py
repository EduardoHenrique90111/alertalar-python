"""Conexão com o PostgreSQL (SQLAlchemy + psycopg).

Cada serviço abre sessões curtas com a fábrica criada aqui. As chamadas às APIs externas ficam
FORA das sessões, para não prender conexões enquanto os serviços públicos respondem.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

FabricaSessoes = sessionmaker[Session]


def criar_engine(url: str, tamanho_pool: int = 10) -> Engine:
    return create_engine(
        url,
        pool_size=tamanho_pool,
        max_overflow=0,
        pool_pre_ping=True,  # bancos gerenciados (ex.: Neon) fecham conexões ociosas
        pool_recycle=300,
        connect_args={"options": "-c timezone=UTC"},
    )


def criar_fabrica(engine: Engine) -> FabricaSessoes:
    # expire_on_commit=False: os objetos continuam legíveis depois que a sessão fecha
    return sessionmaker(bind=engine, expire_on_commit=False)
