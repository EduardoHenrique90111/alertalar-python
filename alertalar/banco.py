from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

FabricaSessoes = sessionmaker[Session]


def criar_engine(url: str, tamanho_pool: int = 10) -> Engine:
    return create_engine(
        url,
        pool_size=tamanho_pool,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"options": "-c timezone=UTC"},
    )


def criar_fabrica(engine: Engine) -> FabricaSessoes:
    return sessionmaker(bind=engine, expire_on_commit=False)
