"""Leitura de planilhas exportadas do S2iD / Atlas Digital (formato CSV)."""

from datetime import date

import pytest

from alertalar.erros import ArquivoInvalido
from alertalar.integracoes.s2id import LeitorRegistrosOficiaisCsv
from alertalar.modelos.enums import TipoEvento

leitor = LeitorRegistrosOficiaisCsv()


def test_le_csv_com_ponto_e_virgula_aspas_e_filtra_somente_hidrologicos():
    csv = """Protocolo;UF;Município;Cod_IBGE_Mun;Data do Evento;COBRADE;Desastre
RS-A-4304606-12100-20240501;RS;Canoas;4304606;01/05/2024;1.2.1.0.0;Inundações
RS-A-4304606-13214-20240120;RS;Canoas;4304606;20/01/2024;1.3.2.1.4;Tempestade Local/Convectiva - Chuvas Intensas
RS-A-4314902-12300-20231110;RS;"Porto Alegre";4314902;10/11/2023 14:00;1.2.3.0.0;Alagamentos
RS-A-4304606-14110-20220110;RS;Canoas;4304606;10/01/2022;1.4.1.1.0;Estiagem
;RS;;;;1.2.2.0.0;Enxurradas
"""
    r = leitor.ler(csv.encode("utf-8"))
    assert r.linhas_lidas == 5
    assert len(r.registros) == 3
    assert r.ignoradas_nao_hidrologicas == 1
    assert r.ignoradas_invalidas == 1
    primeiro = r.registros[0]
    assert primeiro.tipo is TipoEvento.INUNDACAO
    assert primeiro.data == date(2024, 5, 1)
    assert primeiro.codigo_ibge == "4304606"
    # chuvas intensas também causam enchentes (ex.: RS, maio de 2024)
    assert r.registros[1].tipo is TipoEvento.CHUVA_INTENSA
    assert r.registros[2].municipio == "Porto Alegre"
    assert r.registros[2].tipo is TipoEvento.ALAGAMENTO


def test_campo_entre_aspas_com_quebra_de_linha_nao_parte_o_registro():
    csv = ("Protocolo;UF;Município;Data do Evento;COBRADE;Observação\r\n"
           "RS-1;RS;Canoas;05/05/2024;1.2.1.0.0;\"Chuva forte.\r\nRio subiu; bairros ilhados\"\r\n"
           "RS-2;RS;Canoas;06/05/2024;1.2.3.0.0;sem observação\r\n")
    r = leitor.ler(csv.encode("utf-8"))
    assert r.linhas_lidas == 2
    assert len(r.registros) == 2
    assert r.ignoradas_invalidas == 0
    assert r.registros[1].data == date(2024, 5, 6)


def test_aceita_virgula_windows_1252_e_somente_o_ano_do_evento():
    csv = "Sigla_UF,Nome_Municipio,Ano,Tipologia\nSC,São José,2022,Enxurradas\n"
    r = leitor.ler(csv.encode("cp1252"))
    assert len(r.registros) == 1
    reg = r.registros[0]
    assert reg.municipio == "São José"
    assert reg.tipo is TipoEvento.ENXURRADA
    assert reg.somente_ano
    assert reg.data == date(2022, 1, 1)


def test_sem_colunas_obrigatorias_explica_o_que_falta():
    with pytest.raises(ArquivoInvalido) as ex:
        leitor.ler(b"nome;valor\na;1\n")
    assert "UF" in str(ex.value)


def test_arquivo_vazio_e_recusado():
    with pytest.raises(ArquivoInvalido):
        leitor.ler(b"")
