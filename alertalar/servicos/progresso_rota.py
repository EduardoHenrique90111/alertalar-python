from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Etapa(Enum):
    ALTURA = ("Altura da partida e do destino", "o Copernicus DEM (via Open-Meteo)")
    SETORES = ("Áreas de risco no trajeto", "o Serviço Geológico do Brasil (SGB)")
    CAMINHO = ("Caminho pelas ruas", "o Valhalla (ruas do OpenStreetMap)")
    PERFIL = ("Altura ao longo do caminho", "o Copernicus DEM (via Open-Meteo)")

    @property
    def rotulo(self) -> str:
        return self.value[0]

    @property
    def fonte(self) -> str:
        return self.value[1]


class Estado(str, Enum):
    PENDENTE = "PENDENTE"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    FALHOU = "FALHOU"


@dataclass(frozen=True)
class Evento:
    etapa: str
    estado: str
    rotulo: str
    fonte: str
    detalhe: str | None

    def como_json(self) -> dict:
        return {"etapa": self.etapa, "estado": self.estado, "rotulo": self.rotulo, "fonte": self.fonte,
                "detalhe": self.detalhe}


class CalculoCancelado(Exception):
    def __init__(self) -> None:
        super().__init__("Cálculo da rota cancelado.")


class ProgressoRota:
    def informar(self, evento: Evento) -> None:
        pass

    def cancelado(self) -> bool:
        return False


NENHUM = ProgressoRota()
