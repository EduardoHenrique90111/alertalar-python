import time
from datetime import date, datetime, timedelta, timezone

import pytest

from alertalar.erros import IntegracaoExterna
from alertalar.integracoes.http import LimitadorIntervalo
from alertalar.integracoes.ibge import IbgeLocalidadesClient
from alertalar.integracoes.nominatim import NominatimClient
from alertalar.integracoes.open_meteo import ClimaClient, ElevacaoClient
from alertalar.integracoes.overpass import OverpassClient
from alertalar.integracoes.photon import PhotonClient
from alertalar.integracoes.sgb import SgbSetoresRiscoClient
from alertalar.integracoes.viacep import ViaCepClient
from tests.apoio import cliente_http
from tests.apoio import respostas as rs
from tests.apoio.servidor_falso import Resposta, ServidorHttpFalso


@pytest.fixture
def servidor():
    with ServidorHttpFalso() as s:
        yield s


def test_viacep_le_o_endereco_e_trata_cep_inexistente(servidor):
    servidor.rota("/ws/92010000/", Resposta.json(rs.via_cep())).rota("/ws/99999999/",
                                                                      Resposta.json(rs.via_cep_inexistente()))
    cliente = ViaCepClient(cliente_http(), servidor.url("/ws"))
    dados = cliente.buscar("92010-000")
    assert dados.cidade == "Canoas"
    assert dados.codigo_ibge == "4304606"
    assert cliente.buscar("99999999") is None
    cliente.buscar("92010000")
    assert servidor.contar("/ws/92010000/") == 1


def test_photon_busca_so_no_brasil_converte_geojson_e_ignora_outros_paises(servidor):
    servidor.rota("/api", Resposta.json(rs.photon("100")))
    cliente = PhotonClient(cliente_http(), servidor.url(""), LimitadorIntervalo(0.01))

    r = cliente.buscar("Rua de Teste 100, Canoas, Rio Grande do Sul", 10)

    assert len(r) == 3, "o resultado da Argentina fica de fora"
    casa = r[0]
    assert casa.latitude == pytest.approx(rs.LAT, abs=1e-9)
    assert casa.longitude == pytest.approx(rs.LON, abs=1e-9)
    assert casa.place_rank == 30
    assert (casa.numero, casa.rua, casa.bairro, casa.cidade, casa.uf) == ("100", "Rua de Teste", "Centro", "Canoas", "RS")
    assert casa.nome_exibicao == "100, Rua de Teste, Centro, Canoas, Rio Grande do Sul, 92010-000, Brasil"
    assert r[1].place_rank == 26, "a própria rua"
    assert r[1].rua == "Rua de Teste"
    assert r[2].nome_exibicao.startswith("Canoas Shopping, 6750, Avenida Guilherme Schell")
    req = servidor.recebidas[0]
    assert req.caminho == "/api"
    assert req.parametro("q") == "Rua de Teste 100, Canoas, Rio Grande do Sul"
    assert req.parametro("bbox") == "-74.2,-34.0,-28.6,5.5"
    assert req.parametro("limit") == "10"
    assert req.cabecalho("User-Agent").startswith("AlertaLar")


def test_nominatim_envia_busca_estruturada_user_agent_e_respeita_o_intervalo(servidor):
    servidor.rota("/search", Resposta.json(rs.nominatim_numero()))
    cliente = NominatimClient(cliente_http(), servidor.url(""), "contato@exemplo.com", LimitadorIntervalo(0.3))

    inicio = time.monotonic()
    r = cliente.buscar_estruturado("Rua de Teste", "100", "Canoas", "RS", 5)
    cliente.buscar_texto("Rua de Teste, 100, Canoas", 5)
    decorrido = time.monotonic() - inicio

    assert len(r) == 1
    assert (r[0].place_rank, r[0].numero, r[0].uf) == (30, "100", "RS")
    req = servidor.recebidas[0]
    assert req.parametro("street") == "100 Rua de Teste"
    assert req.parametro("state") == "Rio Grande do Sul"
    assert req.parametro("countrycodes") == "br"
    assert req.parametro("email") == "contato@exemplo.com"
    assert req.cabecalho("User-Agent").startswith("AlertaLar")
    assert decorrido >= 0.28, f"intervalo mínimo entre chamadas não respeitado: {decorrido}"


def test_ibge_resolve_codigo_do_municipio_ignorando_acentos(servidor):
    servidor.rota("/estados/RS/municipios", Resposta.json(rs.ibge_municipios_rs()))
    cliente = IbgeLocalidadesClient(cliente_http(), servidor.url(""))
    assert cliente.codigo_municipio("RS", "sao leopoldo") == "4318705"
    assert cliente.codigo_municipio("RS", "Cidade Inexistente") is None


def test_overpass_envia_a_consulta_por_post_e_le_rios_e_corregos(servidor):
    servidor.rota("/api/interpreter", Resposta.json(rs.overpass_com_rio_e_corrego()))
    cliente = OverpassClient(cliente_http(), servidor.url("/api/interpreter"))

    cursos = cliente.buscar_proximos(rs.LAT, rs.LON, 1500)

    assert len(cursos) == 2
    assert cursos[0].principal
    assert cursos[0].descricao() == "rio Rio dos Testes"
    assert not cursos[1].principal
    consulta = servidor.recebidas[0].parametro("data")
    assert "around:1500,-29.920000,-51.180000" in consulta
    assert servidor.recebidas[0].metodo == "POST"


def test_elevacao_envia_varias_coordenadas_numa_unica_requisicao(servidor):
    servidor.rota("/v1/elevation", Resposta.json(rs.elevacao(3)))
    cliente = ElevacaoClient(cliente_http(), servidor.url("/v1/elevation"))
    assert cliente.elevacoes([(-29.9, -51.1), (-29.91, -51.1), (-29.92, -51.1)]) == [4.0, 9.0, 9.0]
    assert servidor.recebidas[0].parametro("latitude") == "-29.900000,-29.910000,-29.920000"


def test_elevacao_com_quantidade_diferente_da_pedida_e_resposta_invalida(servidor):
    servidor.rota("/v1/elevation", Resposta.json('{"elevation":[1.0]}'))
    cliente = ElevacaoClient(cliente_http(), servidor.url("/v1/elevation"))
    with pytest.raises(IntegracaoExterna):
        cliente.elevacoes([(-29.9, -51.1), (-29.91, -51.1)])


def test_sgb_le_setor_com_geometria_e_identifica_risco_hidrologico(servidor):
    servidor.rota("/MapServer/0/query", Resposta.json(rs.sgb_setor_contendo_ponto()))
    cliente = SgbSetoresRiscoClient(cliente_http(), servidor.url("/MapServer/0"))

    setores = cliente.buscar_proximos(rs.LAT, rs.LON, 300)

    assert len(setores) == 1
    s = setores[0]
    assert s.hidrologico
    assert s.grau_risco == "Muito alto"
    assert s.data_setorizacao == date(2024, 1, 1)
    assert s.aneis[0][0][0] == pytest.approx(rs.LAT - 0.001, abs=1e-9)
    req = servidor.recebidas[0]
    assert req.parametro("geometryType") == "esriGeometryPoint"
    assert req.parametro("distance") == "300"


def test_sgb_objeto_error_com_http_200_vira_falha_de_integracao(servidor):
    servidor.rota("/MapServer/0/query", Resposta.json(rs.sgb_erro()))
    cliente = SgbSetoresRiscoClient(cliente_http(), servidor.url("/MapServer/0"))
    with pytest.raises(IntegracaoExterna):
        cliente.buscar_proximos(-29.9, -51.1, 300)


def test_open_meteo_le_series_de_chuva_horaria_e_vazao_diaria(servidor):
    agora = datetime.now(timezone.utc)
    servidor.rota("/v1/forecast", Resposta.json(rs.previsao_chuva(agora))).rota(
        "/v1/flood", Resposta.json(rs.vazao(agora.date())))
    cliente = ClimaClient(cliente_http(), servidor.url("/v1/forecast"), servidor.url("/v1/flood"))

    chuva = cliente.chuva_horaria(-29.92, -51.18)
    vazao = cliente.vazao_diaria(-29.92, -51.18)

    assert chuva.fuso == timezone(timedelta(hours=-3))
    assert len(chuva.horas) == 110
    assert len(vazao.dias) == 15
    assert servidor.recebidas[0].parametro("hourly") == "precipitation"


def test_falhas_http_json_invalido_e_tempo_esgotado_viram_integracao_externa(servidor):
    servidor.rota("/erro500", Resposta.erro(500)).rota("/erro429", Resposta.erro(429, (("Retry-After", "120"),))) \
        .rota("/invalido", Resposta(200, "<html>não é json</html>")).rota("/lento", Resposta(200, "{}", 2.5))
    http = cliente_http(timeout_leitura=0.5)

    with pytest.raises(IntegracaoExterna) as e500:
        http.get_json("Fonte X", servidor.url("/erro500"))
    assert "HTTP 500" in str(e500.value)
    assert e500.value.status_http == 500
    with pytest.raises(IntegracaoExterna) as e429:
        http.get_json("Fonte X", servidor.url("/erro429"))
    assert "limite de requisições" in str(e429.value)
    assert e429.value.espera_pedida == 120
    with pytest.raises(IntegracaoExterna):
        http.get_json("Fonte X", servidor.url("/invalido"))
    with pytest.raises(IntegracaoExterna) as lento:
        http.get_json("Fonte X", servidor.url("/lento"))
    assert lento.value.fonte == "Fonte X"
    assert "Exception" not in str(e500.value) and "Error" not in str(lento.value)
