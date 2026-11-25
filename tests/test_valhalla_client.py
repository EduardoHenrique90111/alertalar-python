"""Cliente do Valhalla contra um servidor local que responde no formato da API real."""

import json

import pytest

from alertalar.erros import IntegracaoExterna
from alertalar.integracoes.http import LimitadorIntervalo
from alertalar.integracoes.valhalla import ModoRota, ValhallaClient, codificar, decodificar
from tests.apoio import cliente_http
from tests.apoio import respostas as rs
from tests.apoio.servidor_falso import Resposta, ServidorHttpFalso

LAT_O, LON_O = -29.92, -51.18
LAT_D, LON_D = -29.9155, -51.1785


@pytest.fixture
def servidor():
    with ServidorHttpFalso() as s:
        yield s


def test_polyline_decodifica_o_exemplo_oficial_e_ida_e_volta_na_precisao_6():
    p = decodificar("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5)
    assert len(p) == 3
    assert p[0] == pytest.approx((38.5, -120.2), abs=1e-9)
    assert p[1] == pytest.approx((40.7, -120.95), abs=1e-9)
    assert p[2] == pytest.approx((43.252, -126.453), abs=1e-9)

    volta = decodificar(codificar([(-29.920001, -51.180002), (-29.915503, -51.178504)], 6), 6)
    assert volta[0][0] == pytest.approx(-29.920001, abs=1e-9)
    assert volta[1][1] == pytest.approx(-51.178504, abs=1e-9)
    assert decodificar("", 6) == []


def test_envia_modo_idioma_e_areas_a_evitar_em_lon_lat_e_le_trajeto(servidor):
    servidor.rota("/route", Resposta.json(rs.valhalla_rota(LAT_O, LON_O, LAT_D, LON_D)))
    cliente = ValhallaClient(cliente_http(), servidor.url(""), "", LimitadorIntervalo(0.01))
    anel = [(-29.918, -51.181), (-29.918, -51.179), (-29.917, -51.179), (-29.918, -51.181)]

    rota = cliente.rota(LAT_O, LON_O, LAT_D, LON_D, ModoRota.A_PE, [anel])

    assert len(rota.pontos) == 3
    assert rota.pontos[0][0] == pytest.approx(LAT_O, abs=1e-6)
    assert rota.pontos[2][1] == pytest.approx(LON_D, abs=1e-6)
    assert rota.distancia_metros == pytest.approx(260, abs=1e-6)
    assert rota.duracao_segundos == pytest.approx(210.5, abs=1e-6)
    assert len(rota.instrucoes) == 3
    assert rota.instrucoes[1].texto == "Vire à esquerda na Rua do Morro."
    assert rota.instrucoes[1].distancia_metros == pytest.approx(110, abs=1e-6)
    assert rota.instrucoes[1].indice_ponto == 1

    req = servidor.recebidas[0]
    assert req.metodo == "POST"
    assert req.cabecalho("Content-Type").startswith("application/json")
    corpo = json.loads(req.corpo)
    assert corpo["costing"] == "pedestrian"
    assert corpo["directions_options"]["language"] == "pt-BR"
    assert corpo["locations"][1]["lat"] == pytest.approx(LAT_D, abs=1e-9)
    primeiro_vertice = corpo["exclude_polygons"][0][0]
    assert primeiro_vertice == pytest.approx([-51.181, -29.918], abs=1e-9), "Valhalla espera [lon, lat]"
    assert "api_key" not in (req.query or ""), "sem chave configurada, nada vai na URL"


def test_de_carro_usa_auto_sem_areas_nao_envia_exclude_polygons_e_chave_vai_na_url(servidor):
    servidor.rota("/route", Resposta.json(rs.valhalla_rota(LAT_O, LON_O, LAT_D, LON_D)))
    cliente = ValhallaClient(cliente_http(), servidor.url("/"), "chave-teste", LimitadorIntervalo(0.01))
    cliente.rota(LAT_O, LON_O, LAT_D, LON_D, ModoRota.CARRO, [])
    req = servidor.recebidas[0]
    corpo = json.loads(req.corpo)
    assert corpo["costing"] == "auto"
    assert "exclude_polygons" not in corpo
    assert req.parametro("api_key") == "chave-teste"


def test_sem_caminho_fora_do_ar_ou_vazio_vira_falha_de_integracao(servidor):
    servidor.rota("/sem-caminho/route", Resposta(400, rs.valhalla_sem_caminho())) \
        .rota("/fora/route", Resposta.erro(500)).rota("/vazio/route", Resposta.json('{"trip":{"legs":[]}}'))
    limitador = LimitadorIntervalo(0.01)
    for caminho in ("/sem-caminho", "/fora", "/vazio"):
        cliente = ValhallaClient(cliente_http(), servidor.url(caminho), "", limitador)
        with pytest.raises(IntegracaoExterna):
            cliente.rota(LAT_O, LON_O, LAT_D, LON_D, ModoRota.A_PE, [])
