import importlib
import re
from datetime import date
from functools import cache

atlas = importlib.import_module("alertalar.migracoes.V4__historico_oficial_atlas")
Registro = atlas.Registro


@cache
def base() -> tuple:
    with atlas.abrir_recurso() as arquivo:
        cabecalho = arquivo.readline()
        assert cabecalho.startswith("protocolo;uf;municipio;ibge;data;cobrade;tipologia;status"), cabecalho
        return tuple(Registro.de(linha.rstrip("\n")) for linha in arquivo)


def test_base_embutida_tem_27581_registros_validos_de_1991_a_2025():
    registros = base()
    assert len(registros) == 27_581
    protocolos = set()
    for r in registros:
        assert r.protocolo not in protocolos, f"protocolo repetido: {r.protocolo}"
        protocolos.add(r.protocolo)
        assert r.tipo_evento() in {"INUNDACAO", "ENXURRADA", "ALAGAMENTO", "CHUVA_INTENSA"}, r.tipologia
        assert re.fullmatch(r"\d{7}", r.ibge), r.ibge
        assert len(r.uf) == 2
        assert date(1991, 1, 1) <= r.data <= date(2025, 12, 31)
        assert len(r.descricao()) <= 2000


def test_enchentes_de_maio_de_2024_em_canoas_e_porto_alegre_estao_na_base():
    registros = base()
    canoas = next((r for r in registros if r.ibge == "4304606" and r.data == date(2024, 5, 2)), None)
    assert canoas is not None
    assert canoas.tipo_evento() == "CHUVA_INTENSA"
    assert "reconhecida pela União" in canoas.descricao()
    assert any(r.ibge == "4314902" and r.data == date(2024, 4, 29) for r in registros)


def test_registro_vira_descricao_legivel_com_cobrade_reconhecimento_danos_e_fonte():
    r = Registro.de("RS-A-4304606-12100-20240502;RS;Canoas;4304606;2024-05-02;12100;Inundações;Reconhecido;"
                    "31;12000;1;1500;0")
    assert r.tipo_evento() == "INUNDACAO"
    d = r.descricao()
    assert d.startswith("Inundação registrada pelo município (COBRADE 1.2.1.0.0)."), d
    assert "31 mortes, 12.000 pessoas desabrigadas, 1 pessoa desalojada, 1.500 casas danificadas" in d
    assert "destruída" not in d
    assert "Protocolo S2iD RS-A-4304606-12100-20240502" in d
    assert "Atlas Digital de Desastres no Brasil v1.1" in d

    sem_danos = Registro.de("SC-1;SC;Blumenau;4202404;2011-09-08;13214;Chuvas Intensas;Registro;0;0;0;0;0")
    assert sem_danos.tipo_evento() == "CHUVA_INTENSA"
    assert "Registrado no S2iD, sem reconhecimento federal." in sem_danos.descricao()
    assert "Sem danos humanos ou habitacionais informados." in sem_danos.descricao()
