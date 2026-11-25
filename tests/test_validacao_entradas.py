"""Validação de endereços, relatos e cadastro."""

from datetime import date, timedelta

import pytest

from alertalar.erros import DadosInvalidos
from alertalar.esquemas import EnderecoRequest, OcorrenciaRequest, RegistroRequest
from alertalar.modelos.enums import TipoEvento


def endereco(cep, rua, cidade, uf, lat=None, lon=None, numero="100"):
    return EnderecoRequest(cep=cep, rua=rua, numero=numero, bairro="Centro", cidade=cidade, estado=uf, latitude=lat,
                           longitude=lon)


def campos_invalidos(pedido) -> set[str]:
    try:
        pedido.validar()
        return set()
    except DadosInvalidos as e:
        return set(e.erros)


def test_endereco_completo_e_valido_nao_gera_erros():
    assert campos_invalidos(endereco("92010-000", "Rua A", "Canoas", "RS")) == set()
    assert campos_invalidos(endereco(None, "Rua A", "Canoas", "RS", -29.9, -51.1)) == set()


@pytest.mark.parametrize("cep", ["123", "9201-0000", "abcde-fgh", "920100000"])
def test_cep_com_formato_invalido_e_rejeitado(cep):
    assert "cep" in campos_invalidos(endereco(cep, "Rua A", "Canoas", "RS"))


def test_rua_cidade_e_uf_sao_obrigatorias_e_a_uf_precisa_existir():
    assert {"rua", "cidade", "estado"} <= campos_invalidos(endereco(None, " ", "", "XX"))


def test_coordenadas_fora_do_brasil_ou_incompletas_sao_rejeitadas():
    assert "latitude" in campos_invalidos(endereco(None, "Rua A", "Canoas", "RS", 40.7, -74.0))
    assert "coordenadasCompletas" in campos_invalidos(endereco(None, "Rua A", "Canoas", "RS", -29.9, None))


def test_numero_aceita_apenas_caracteres_seguros():
    assert "numero" in campos_invalidos(endereco(None, "Rua A", "Canoas", "RS", numero="<script>"))


def test_relato_exige_data_no_passado_descricao_minima_e_declaracao_de_veracidade():
    r = OcorrenciaRequest(localizacao="Rua A, 10", municipio="Canoas", estado="RS",
                          data_ocorrencia=date.today() + timedelta(days=2), descricao="curta",
                          tipo_evento=TipoEvento.ALAGAMENTO, contato_relator="email-invalido",
                          declaracao_veracidade=False)
    assert {"dataOcorrencia", "descricao", "contatoRelator", "declaracaoVeracidade"} <= campos_invalidos(r)


def test_senha_precisa_ter_letras_e_numeros_e_no_minimo_8_caracteres():
    assert campos_invalidos(RegistroRequest(nome="Ana", email="ana@exemplo.com", senha="abcdefgh")) == {"senha"}
    assert campos_invalidos(RegistroRequest(nome="Ana", email="ana@exemplo.com", senha="abc12345")) == set()


def test_le_o_json_do_front_end_com_nomes_em_camel_case():
    r = OcorrenciaRequest.model_validate({"localizacao": "Rua A, 10", "dataOcorrencia": "2024-05-03",
                                          "tipoEvento": "ALAGAMENTO", "declaracaoVeracidade": True,
                                          "latitude": "-29.9", "numero_ignorado": 1})
    assert r.data_ocorrencia == date(2024, 5, 3)
    assert r.tipo_evento is TipoEvento.ALAGAMENTO
    assert r.latitude == -29.9
