"""Ferramenta de linha de comando (não faz parte do servidor) que gera a base compacta de desastres
ligados a chuva a partir do CSV oficial do Atlas Digital de Desastres no Brasil (MIDR/Sedec,
registros do S2iD). O resultado é gravado em ``alertalar/dados/`` e carregado no banco pela
migração de histórico oficial (V4).

Uso::

    python -m alertalar.ferramentas.preparar_base_atlas \\
        BD_Atlas_1991_2025_v1.1_2026.08.06_Consolidado.csv \\
        alertalar/dados/atlas-desastres-chuva.csv.gz \\
        alertalar/dados/municipios-ibge.csv.gz

Baixe o CSV em https://atlasdigital.mdr.gov.br (página Downloads). O arquivo oficial vem em
Windows-1252 com separador ";".
"""

from __future__ import annotations

import gzip
import io
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alertalar.integracoes.s2id import dividir
from alertalar.util.numeros import arredondar

# Tipologias aproveitadas (descricao_tipologia do Atlas)
TIPOLOGIAS = frozenset({"Inundações", "Enxurradas", "Alagamentos", "Chuvas Intensas"})

COLUNAS_SAIDA = ("protocolo", "uf", "municipio", "ibge", "data", "cobrade", "tipologia", "status", "mortos",
                 "desabrigados", "desalojados", "casas_danificadas", "casas_destruidas")

COLUNAS_ATLAS = ("Protocolo_S2iD", "Sigla_UF", "Nome_Municipio", "Cod_IBGE_Mun", "Data_Evento", "Cod_Cobrade",
                 "descricao_tipologia", "Status", "DH_MORTOS", "DH_DESABRIGADOS", "DH_DESALOJADOS",
                 "DM_Uni Habita Danificadas", "DM_Uni Habita Destruidas")


@dataclass(frozen=True)
class Resultado:
    """``municipios``: código IBGE, UF e cada grafia do nome que aparece no Atlas (todas as
    tipologias, não só as de chuva), ordenados por código e nome."""

    linhas: list[list[str]]
    lidas: int
    outras_tipologias: int
    invalidos: int
    por_tipologia: dict[str, int]
    municipios: list[list[str]]


def converter(entrada: io.TextIOBase) -> Resultado:
    cabecalho = entrada.readline()
    if not cabecalho:
        raise ValueError("Arquivo vazio")
    cabecalho = cabecalho.rstrip("\r\n").lstrip("﻿")
    indice: dict[str, int] = {}
    for i, nome in enumerate(dividir(cabecalho, ";")):
        indice.setdefault(nome.strip(), i)
    pos = []
    for coluna in COLUNAS_ATLAS:
        if coluna not in indice:
            raise ValueError(f"Coluna obrigatória ausente no CSV do Atlas: {coluna}")
        pos.append(indice[coluna])

    saida: list[list[str]] = []
    por_tipologia: Counter[str] = Counter()
    municipios: set[str] = set()
    lidas = outras = invalidos = 0
    while (linha := _ler_registro(entrada)) is not None:
        if not linha.strip():
            continue
        lidas += 1
        campos = dividir(linha, ";")

        def campo(i: int) -> str:
            return campos[pos[i]].strip() if pos[i] < len(campos) else ""

        codigo_municipio, uf, nome_municipio = campo(3), campo(1).upper(), campo(2).replace(";", ",")
        if re.fullmatch(r"\d{7}", codigo_municipio) and len(uf) == 2 and nome_municipio:
            municipios.add(f"{codigo_municipio};{uf};{nome_municipio}")
        tipologia = campo(6)
        if tipologia not in TIPOLOGIAS:
            outras += 1
            continue
        protocolo = campo(0)
        try:
            data = datetime.strptime(campo(4), "%d/%m/%Y").date() if re.fullmatch(r"\d{2}/\d{2}/\d{4}", campo(4)) \
                else None
        except ValueError:
            data = None
        if data is None:
            invalidos += 1
            continue
        if not protocolo or len(uf) != 2 or not re.fullmatch(r"\d{7}", codigo_municipio) or not nome_municipio:
            invalidos += 1
            continue
        saida.append([protocolo, uf, nome_municipio, codigo_municipio, data.isoformat(), campo(5), tipologia, campo(7),
                      _inteiro(campo(8)), _inteiro(campo(9)), _inteiro(campo(10)), _inteiro(campo(11)),
                      _inteiro(campo(12))])
        por_tipologia[tipologia] += 1
    # Ordenado por município e data: comprime melhor e facilita conferências
    saida.sort(key=lambda r: (r[3], r[4], r[0]))
    lista_municipios = [m.split(";", 2) for m in sorted(municipios)]
    return Resultado(saida, lidas, outras, invalidos, dict(sorted(por_tipologia.items())), lista_municipios)


def _ler_registro(entrada: io.TextIOBase) -> str | None:
    """Um registro completo: campos entre aspas podem conter quebras de linha (ex.: descrições de
    danos), então as linhas são juntadas enquanto houver aspas abertas."""
    linha = entrada.readline()
    if not linha:
        return None
    texto = linha.rstrip("\r\n")
    while texto.count('"') % 2 == 1:
        continuacao = entrada.readline()
        if not continuacao:
            break
        texto += "\n" + continuacao.rstrip("\r\n")
    return texto


def _inteiro(valor: str) -> str:
    v = valor.replace(".", "").replace(",", ".").strip()
    if not v:
        return "0"
    try:
        return str(max(0, arredondar(float(v))))
    except ValueError:
        return "0"


def main(argumentos: list[str]) -> int:
    if len(argumentos) not in (2, 3):
        print("Uso: python -m alertalar.ferramentas.preparar_base_atlas <CSV do Atlas> <saida.csv.gz> "
              "[municipios.csv.gz]", file=sys.stderr)
        return 2
    with open(argumentos[0], encoding="cp1252", newline="") as entrada:
        r = converter(entrada)
    saida = Path(argumentos[1])
    saida.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(saida, "wt", encoding="utf-8", newline="\n") as w:
        w.write(";".join(COLUNAS_SAIDA) + "\n")
        for linha in r.linhas:
            w.write(";".join(linha) + "\n")
    if len(argumentos) == 3:
        arquivo_municipios = Path(argumentos[2])
        with gzip.open(arquivo_municipios, "wt", encoding="utf-8", newline="\n") as w:
            w.write("codigo;uf;nome\n")
            for m in r.municipios:
                w.write(";".join(m) + "\n")
        print(f"Municípios (código e grafias do nome): {len(r.municipios)} linhas em {arquivo_municipios}")
    print(f"Linhas lidas: {r.lidas}\nRegistros gravados: {len(r.linhas)}\nIgnorados (outras tipologias): "
          f"{r.outras_tipologias}\nDescartados (dados inválidos): {r.invalidos}\nPor tipologia: {r.por_tipologia}\n"
          f"Arquivo: {saida} ({saida.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
