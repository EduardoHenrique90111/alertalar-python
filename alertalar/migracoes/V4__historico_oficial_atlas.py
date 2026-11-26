from __future__ import annotations

import gzip
import io
import logging
import re
from dataclasses import dataclass
from datetime import date
from importlib import resources

from sqlalchemy import Connection, text

from alertalar.util.numeros import inteiro_br

log = logging.getLogger("alertalar.migracoes")

RECURSO = "atlas-desastres-chuva.csv.gz"
VERSAO_BASE = "Atlas Digital de Desastres no Brasil v1.1 (MIDR/Sedec, 06/08/2026)"
LINHAS_POR_COMANDO = 500

_INSERIR = text("""
    INSERT INTO ocorrencia (localizacao, municipio, estado, codigo_ibge, data_ocorrencia, descricao, tipo_evento,
                            origem, status_validacao, nivel_localizacao, fonte_id, identificador_externo,
                            data_validacao, data_registro)
    VALUES (:localizacao, :municipio, :estado, :codigo_ibge, :data_ocorrencia, :descricao, :tipo_evento,
            'OFICIAL', 'CONFIRMADA', 'MUNICIPIO', :fonte_id, :identificador_externo, now(), now())
    ON CONFLICT (fonte_id, identificador_externo) WHERE identificador_externo IS NOT NULL DO NOTHING""")


@dataclass(frozen=True)
class Registro:
    protocolo: str
    uf: str
    municipio: str
    ibge: str
    data: date
    cobrade: str
    tipologia: str
    status: str
    mortos: int
    desabrigados: int
    desalojados: int
    casas_danificadas: int
    casas_destruidas: int

    @staticmethod
    def de(linha: str) -> Registro:
        c = linha.split(";")
        if len(c) < 13:
            raise ValueError(f"Linha inválida na base do Atlas: {linha}")
        return Registro(c[0], c[1], c[2], c[3], date.fromisoformat(c[4]), c[5], c[6], c[7], int(c[8]), int(c[9]),
                        int(c[10]), int(c[11]), int(c[12]))

    def tipo_evento(self) -> str:
        return {"Inundações": "INUNDACAO", "Enxurradas": "ENXURRADA", "Alagamentos": "ALAGAMENTO",
                "Chuvas Intensas": "CHUVA_INTENSA"}.get(self.tipologia, "OUTRO")

    def descricao(self) -> str:
        evento = {"Inundações": "Inundação registrada", "Enxurradas": "Enxurrada registrada",
                  "Alagamentos": "Alagamento registrado", "Chuvas Intensas": "Chuvas intensas registradas"}.get(
            self.tipologia, f"{self.tipologia} (registro)")
        texto = evento + " pelo município"
        if re.fullmatch(r"\d{5}", self.cobrade):
            texto += f" (COBRADE {'.'.join(self.cobrade)})"
        texto += ". " + ("Situação de emergência ou calamidade reconhecida pela União."
                         if self.status.lower() == "reconhecido" else "Registrado no S2iD, sem reconhecimento federal.")
        danos = []
        _adicionar(danos, self.mortos, "morte", "mortes")
        _adicionar(danos, self.desabrigados, "pessoa desabrigada", "pessoas desabrigadas")
        _adicionar(danos, self.desalojados, "pessoa desalojada", "pessoas desalojadas")
        _adicionar(danos, self.casas_danificadas, "casa danificada", "casas danificadas")
        _adicionar(danos, self.casas_destruidas, "casa destruída", "casas destruídas")
        texto += (" Sem danos humanos ou habitacionais informados." if not danos
                  else " Danos informados: " + ", ".join(danos) + ".")
        texto += f" Protocolo S2iD {self.protocolo}. Fonte: {VERSAO_BASE}."
        return texto[:1999] if len(texto) > 2000 else texto


def _adicionar(lista: list[str], n: int, singular: str, plural: str) -> None:
    if n > 0:
        lista.append(f"{inteiro_br(n)} {singular if n == 1 else plural}")


def abrir_recurso() -> io.TextIOBase:
    dados = resources.files("alertalar.dados").joinpath(RECURSO).read_bytes()
    return io.TextIOWrapper(io.BytesIO(gzip.decompress(dados)), encoding="utf-8")


def migrar(conexao: Connection, leitor: io.TextIOBase | None = None) -> int:
    fonte_id = conexao.execute(text("SELECT id FROM fonte_dados WHERE codigo = 'S2ID_RECONHECIMENTOS'")).scalar()
    if fonte_id is None:
        raise RuntimeError("Fonte S2ID_RECONHECIMENTOS não cadastrada")
    inseridos = 0
    with leitor or abrir_recurso() as arquivo:
        cabecalho = arquivo.readline().rstrip("\r\n")
        if not cabecalho.startswith("protocolo;uf;municipio;ibge;data"):
            raise RuntimeError(f"Base do Atlas em formato inesperado: {cabecalho}")
        lote: list[dict] = []
        for linha in arquivo:
            linha = linha.rstrip("\r\n")
            if not linha.strip():
                continue
            r = Registro.de(linha)
            lote.append({"localizacao": f"Município de {r.municipio}/{r.uf} (registro municipal, sem endereço específico)",
                         "municipio": r.municipio, "estado": r.uf, "codigo_ibge": r.ibge, "data_ocorrencia": r.data,
                         "descricao": r.descricao(), "tipo_evento": r.tipo_evento(), "fonte_id": fonte_id,
                         "identificador_externo": "PROT:" + r.protocolo})
            if len(lote) == LINHAS_POR_COMANDO:
                inseridos += conexao.execute(_INSERIR, lote).rowcount
                lote = []
        if lote:
            inseridos += conexao.execute(_INSERIR, lote).rowcount
    conexao.execute(text("""
        UPDATE fonte_dados
           SET nome = :nome, url = :url, status_integracao = 'ATIVA', data_atualizacao = :data, descricao = :descricao
         WHERE id = :id"""), {
        "nome": "MIDR/Sedec - Atlas Digital de Desastres no Brasil (registros do S2iD)",
        "url": "https://atlasdigital.mdr.gov.br",
        "data": "2026-08-06T00:00:00-03:00",
        "descricao": "Registros oficiais de desastres ligados a chuva (inundações, enxurradas, alagamentos e chuvas "
                     "intensas) de todos os municípios, 1991 a 2025, incluídos no sistema a partir da base consolidada "
                     "v1.1 de 06/08/2026. São registros municipais: indicam que a cidade foi afetada, não qual rua. "
                     "Versões mais novas podem ser importadas pela tela de Moderação.",
        "id": fonte_id})
    log.info("Histórico oficial carregado: %d registros (%s)", inseridos, VERSAO_BASE)
    return inseridos
