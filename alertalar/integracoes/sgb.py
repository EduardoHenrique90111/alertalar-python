from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from alertalar.erros import IntegracaoExterna
from alertalar.integracoes import http
from alertalar.integracoes.http import ClienteHttpExterno
from alertalar.util import texto as txt

FONTE = "Serviço Geológico do Brasil - Setorização de Riscos"

Anel = tuple[tuple[float, float], ...]


@dataclass(frozen=True, eq=False)
class SetorRisco:
    municipio: str | None
    uf: str | None
    numero_setor: str | None
    local: str | None
    tipologia: str | None
    grau_risco: str | None
    descricao: str | None
    data_setorizacao: date | None
    hidrologico: bool
    aneis: tuple[Anel, ...]


class SgbSetoresRiscoClient:
    def __init__(self, cliente: ClienteHttpExterno, url_camada: str):
        self.http = cliente
        self.url_camada = http.sem_barra_final(url_camada)

    def buscar_proximos(self, lat: float, lon: float, raio_metros: int) -> list[SetorRisco]:
        p = {"geometry": f"{lon:.6f},{lat:.6f}", "geometryType": "esriGeometryPoint", "inSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "distance": int(raio_metros), "units": "esriSRUnit_Meter",
             "outFields": "*", "returnGeometry": "true", "outSR": 4326, "f": "json"}
        dados = self.http.get_json(FONTE, http.uri(self.url_camada + "/query", p))
        if isinstance(dados, dict) and "error" in dados:
            msg = http.texto(dados.get("error"), "message")
            raise IntegracaoExterna(FONTE, "O serviço do SGB recusou a consulta" + ("." if msg is None else ": " + msg))
        return [interpretar(f) for f in http.lista(http.campo(dados, "features"))]


def interpretar(feature) -> SetorRisco:
    atributos = {}
    for nome, valor in (http.campo(feature, "attributes") or {}).items():
        curto = nome[nome.rfind(".") + 1:] if "." in nome else nome
        atributos[curto.lower()] = valor
    tipologias = []
    texto_busca = []
    for i in range(1, 6):
        g = _texto(atributos, f"tipolo_g{i}")
        e = _texto(atributos, f"tipolo_e{i}")
        c = _texto(atributos, f"cobrade_{i:02d}")
        if e is not None or g is not None:
            tipologias.append(e if e is not None else g)
        texto_busca += [str(g), str(e), str(c)]
    descricao = _texto(atributos, "descricao")
    texto_busca.append(str(descricao))

    data_ms = http.numero(atributos.get("data_setor"))
    data = None if data_ms is None else datetime.fromtimestamp(int(data_ms) / 1000, timezone.utc).date()

    aneis = []
    for anel in http.lista(http.campo(http.campo(feature, "geometry"), "rings")):
        pontos = []
        for xy in http.lista(anel):
            x = http.numero(xy[0]) if isinstance(xy, list) and len(xy) > 0 else None
            y = http.numero(xy[1]) if isinstance(xy, list) and len(xy) > 1 else None
            if x is not None and y is not None:
                pontos.append((y, x))
        if len(pontos) >= 3:
            aneis.append(tuple(pontos))
    return SetorRisco(_texto(atributos, "munic"), _texto(atributos, "uf"), _texto(atributos, "num_setor"),
                      _texto(atributos, "local"), "; ".join(tipologias) or None, _texto(atributos, "grau_risco"),
                      descricao, data, eh_hidrologico(" ".join(texto_busca)), tuple(aneis))


def eh_hidrologico(texto: str) -> bool:
    n = txt.normalizar(texto)
    return ("inunda" in n or "enxurr" in n or "alaga" in n or "hidrolog" in n
            or re.search(r"\b1\.2\.[123]", n) is not None)


def _texto(atributos: dict, campo: str) -> str | None:
    v = atributos.get(campo)
    if v is None:
        return None
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (str, int, float)):
        s = v if isinstance(v, str) else str(v)
    else:
        return None
    return s.strip() or None
