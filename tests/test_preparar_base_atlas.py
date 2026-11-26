import io

from alertalar.ferramentas.preparar_base_atlas import converter


def test_conversao_do_csv_original_campo_com_quebra_de_linha_filtro_e_ordenacao():
    csv = ('"Protocolo_S2iD";"Nome_Municipio";"Sigla_UF";"Data_Evento";"Cod_Cobrade";"descricao_tipologia";'
           '"Status";"Cod_IBGE_Mun";"DH_MORTOS";"DH_DESABRIGADOS";"DH_DESALOJADOS";'
           '"DM_Uni Habita Danificadas";"DM_Uni Habita Destruidas";"Observacao"\r\n'
           'SP-2;São Paulo;SP;10/02/2020;12300;Alagamentos;Registro;3550308;0;0;0;0;0;""\r\n'
           'RS-1;Canoas;RS;02/05/2024;13214;Chuvas Intensas;Reconhecido;4304606;31;"12.000";0;0;0;"Água subiu;\r\n'
           'bairros ilhados"\r\n'
           'RS-3;Canoas;RS;01/01/2022;14110;Estiagem e Seca;Reconhecido;4304606;0;0;0;0;0;\r\n'
           'RS-4;Canoas;RS;data ruim;12100;Inundações;Registro;4304606;0;0;0;0;0;\r\n')
    entrada = io.TextIOWrapper(io.BytesIO(csv.encode("cp1252")), encoding="cp1252", newline="")
    r = converter(entrada)
    assert r.lidas == 4
    assert r.outras_tipologias == 1
    assert r.invalidos == 1
    assert len(r.linhas) == 2
    primeiro = r.linhas[0]
    assert primeiro[0] == "SP-2"
    assert primeiro[2] == "São Paulo"
    canoas = r.linhas[1]
    assert canoas[4] == "2024-05-02"
    assert canoas[6] == "Chuvas Intensas"
    assert canoas[9] == "12000"
    assert ["4304606", "RS", "Canoas"] in r.municipios
