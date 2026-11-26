import pytest

from alertalar.util import geo, numeros, texto
from alertalar.util.uf import UnidadeFederativa


def test_normaliza_texto_removendo_acentos_caixa_e_espacos():
    assert texto.normalizar("  São José   do NORTE ") == "sao jose do norte"
    assert texto.normalizar(None) == ""


def test_limpa_caracteres_de_controle_de_textos_livres():
    assert texto.limpar("  Rua\u0000 A  ") == "Rua A"
    assert texto.limpar("   ") is None


def test_formata_cep_somente_quando_ha_8_digitos():
    assert texto.formatar_cep("92010000") == "92010-000"
    assert texto.formatar_cep("92010-000") == "92010-000"
    assert texto.formatar_cep("9201") is None


def test_reconhece_uf_por_sigla_ou_nome():
    assert UnidadeFederativa.de_texto("rs") is UnidadeFederativa.RS
    assert UnidadeFederativa.de_texto("Sao Paulo") is UnidadeFederativa.SP
    assert UnidadeFederativa.de_texto("XX") is None


def test_distancia_de_haversine_entre_pontos_conhecidos():
    assert geo.distancia_metros(-29.90, -51.18, -29.91, -51.18) == pytest.approx(1112, abs=5)


def test_ponto_mais_proximo_de_uma_linha_esta_sobre_o_segmento():
    linha = [(-29.91, -51.17), (-29.93, -51.17)]
    p = geo.ponto_mais_proximo(-29.92, -51.18, linha)
    assert p[0] == pytest.approx(-29.92, abs=1e-4)
    assert p[1] == pytest.approx(-51.17, abs=1e-6)
    assert p[2] == pytest.approx(geo.distancia_metros(-29.92, -51.18, -29.92, -51.17), abs=2)


def test_ponto_dentro_e_fora_de_poligono():
    quadrado = [(0, 0), (0, 1), (1, 1), (1, 0)]
    assert geo.dentro_do_poligono(0.5, 0.5, quadrado)
    assert not geo.dentro_do_poligono(1.5, 0.5, quadrado)


def test_limites_do_territorio_brasileiro():
    assert geo.dentro_do_brasil(-29.9, -51.1)
    assert not geo.dentro_do_brasil(40.7, -74.0)


def test_deslocamento_por_distancia_e_rumo():
    p = geo.deslocar(-29.9, -51.1, 300, 0)
    assert geo.distancia_metros(-29.9, -51.1, p[0], p[1]) == pytest.approx(300, abs=1)
    assert p[0] > -29.9


def test_arredonda_empates_para_cima_como_nos_textos():
    assert numeros.arredondar(2.5) == 3
    assert numeros.arredondar(-2.5) == -2
    assert numeros.decimal(0.125, 2) == "0.13"
    assert numeros.decimal(2.25, 1, virgula=True) == "2,3"
    assert numeros.inteiro_br(12000) == "12.000"


def test_direcao_pelo_rumo():
    assert geo.direcao(0) == "norte"
    assert geo.direcao(100) == "leste"
    assert geo.direcao(-45) == "noroeste"
