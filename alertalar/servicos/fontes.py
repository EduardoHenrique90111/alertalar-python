from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from alertalar.modelos.entidades import FonteDados
from alertalar.repositorios import FonteDadosRepositorio

log = logging.getLogger("alertalar.fontes")

INTERVALO_GRAVACAO = timedelta(minutes=10)


class FonteDadosService:
    def __init__(self, repositorio: FonteDadosRepositorio):
        self.repositorio = repositorio
        self._ultima_gravacao: dict[str, datetime] = {}
        self._trava = threading.Lock()

    def listar(self) -> list[FonteDados]:
        return self.repositorio.todas_por_id()

    def buscar(self, codigo: str) -> FonteDados | None:
        return self.repositorio.por_codigo(codigo)

    def obrigatoria(self, codigo: str) -> FonteDados:
        fonte = self.repositorio.por_codigo(codigo)
        if fonte is None:
            raise RuntimeError(f"Fonte de dados não cadastrada: {codigo}")
        return fonte

    def registrar_acesso(self, codigo: str, quando: datetime) -> None:
        with self._trava:
            anterior = self._ultima_gravacao.get(codigo)
            if anterior is not None and quando - anterior < INTERVALO_GRAVACAO:
                return
        try:
            fonte = self.repositorio.por_codigo(codigo)
            if fonte is not None:
                fonte.data_atualizacao = quando
                self.repositorio.salvar(fonte)
            with self._trava:
                self._ultima_gravacao[codigo] = quando
        except Exception:
            log.warning("Não foi possível registrar o acesso à fonte %s", codigo, exc_info=True)
