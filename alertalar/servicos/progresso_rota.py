"""Andamento do cálculo da rota segura, etapa por etapa.

A tela usa esses avisos para mostrar sobre o mapa o que está sendo consultado (e em qual fonte)
enquanto o caminho não chega: cada etapa é uma consulta real a um serviço externo, nada é estimado
pelo tempo. Os avisos podem chegar de threads diferentes (altura e áreas de risco são consultadas
ao mesmo tempo); quem implementa precisa aceitar chamadas simultâneas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Etapa(Enum):
    """Etapas do cálculo, na ordem em que aparecem para a pessoa: (rótulo, fonte)."""

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
    PENDENTE = "PENDENTE"  # ainda vai acontecer
    EM_ANDAMENTO = "EM_ANDAMENTO"  # consulta enviada, aguardando a resposta do serviço
    CONCLUIDA = "CONCLUIDA"
    FALHOU = "FALHOU"


@dataclass(frozen=True)
class Evento:
    """``etapa``: ALTURA, SETORES, CAMINHO ou PERFIL; ``rotulo``: o que está sendo feito;
    ``fonte``: serviço consultado, já com artigo para a frase "Consultando o …" da tela;
    ``detalhe``: complemento (ex.: "desviando de 3 áreas de risco"), pode ser None."""

    etapa: str
    estado: str
    rotulo: str
    fonte: str
    detalhe: str | None

    def como_json(self) -> dict:
        return {"etapa": self.etapa, "estado": self.estado, "rotulo": self.rotulo, "fonte": self.fonte,
                "detalhe": self.detalhe}


class CalculoCancelado(Exception):
    """O cálculo foi interrompido porque a pessoa desistiu."""

    def __init__(self) -> None:
        super().__init__("Cálculo da rota cancelado.")


class ProgressoRota:
    """Quem acompanha o cálculo. A implementação padrão não faz nada."""

    def informar(self, evento: Evento) -> None:
        pass

    def cancelado(self) -> bool:
        """True quando a pessoa desistiu (cancelou ou fechou a página): o cálculo para antes da
        próxima consulta externa, sem gastar o limite de uso dos serviços públicos."""
        return False


NENHUM = ProgressoRota()
