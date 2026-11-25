"""Geocodificação e validação de endereços (APIs externas simuladas com unittest.mock)."""

from unittest.mock import Mock

import pytest

from alertalar.erros import EnderecoNaoEncontrado, IntegracaoExterna, PrecisaoInsuficiente
from alertalar.esquemas import EnderecoRequest
from alertalar.integracoes.ibge import IbgeLocalidadesClient, MunicipiosIbge
from alertalar.integracoes.nominatim import NominatimClient, ResultadoGeocodificacao
from alertalar.integracoes.photon import PhotonClient
from alertalar.integracoes.viacep import DadosCep, ViaCepClient
from alertalar.modelos.entidades import Endereco
from alertalar.modelos.enums import PrecisaoGeocodificacao
from alertalar.repositorios import EnderecoRepositorio
from alertalar.servicos.enderecos import EnderecoService
from alertalar.servicos.fontes import FonteDadosService
from alertalar.servicos.geocodificacao import GeocodificacaoService, nome_junto


class Dubles:
    def __init__(self) -> None:
        self.via_cep = Mock(spec=ViaCepClient)
        self.via_cep.buscar.return_value = None
        self.nominatim = Mock(spec=NominatimClient)
        self.nominatim.buscar_estruturado.return_value = []
        self.nominatim.buscar_texto.return_value = []
        self.photon = Mock(spec=PhotonClient)
        self.photon.buscar.return_value = []
        self.ibge = Mock(spec=IbgeLocalidadesClient)
        self.ibge.codigo_municipio.return_value = None
        self.repositorio = Mock(spec=EnderecoRepositorio)
        self.repositorio.salvar.side_effect = lambda e: e
        self.repositorio.por_chave.return_value = None
        self.fontes = Mock(spec=FonteDadosService)

    def servico(self, municipios: MunicipiosIbge | None = None) -> EnderecoService:
        return EnderecoService(self.via_cep, GeocodificacaoService(self.nominatim, self.photon, self.fontes), self.ibge,
                               municipios or MunicipiosIbge.vazio(), self.repositorio, self.fontes)


@pytest.fixture
def d() -> Dubles:
    return Dubles()


def req(numero: str | None) -> EnderecoRequest:
    return EnderecoRequest(rua="Rua de Teste", numero=numero, bairro="Centro", cidade="Canoas", estado="RS")


def resultado(rank: int, numero: str | None, cidade: str, uf: str) -> ResultadoGeocodificacao:
    return ResultadoGeocodificacao(-29.92, -51.18, rank, "road", numero, "Rua de Teste", "Centro", cidade, uf, None,
                                   "Rua de Teste, Canoas")


def test_numero_encontrado_gera_precisao_numero_e_codigo_ibge(d):
    d.nominatim.buscar_estruturado.return_value = [resultado(30, "100", "Canoas", "RS")]
    d.ibge.codigo_municipio.side_effect = lambda uf, cidade: "4304606" if (uf, cidade) == ("RS", "Canoas") else None

    e = d.servico().resolver_para_analise(req("100"))

    d.nominatim.buscar_estruturado.assert_called_once_with("Rua de Teste", "100", "Canoas", "RS", 5)
    assert e.precisao == PrecisaoGeocodificacao.NUMERO
    assert e.codigo_ibge == "4304606"
    assert e.latitude == -29.92
    assert e.chave_normalizada is not None


def test_somente_a_rua_encontrada_gera_precisao_rua(d):
    d.nominatim.buscar_estruturado.return_value = [resultado(26, None, "Canoas", "RS")]
    assert d.servico().resolver_para_analise(req("100")).precisao == PrecisaoGeocodificacao.RUA


def test_resultado_so_no_nivel_de_cidade_nao_e_analisado(d):
    d.nominatim.buscar_estruturado.return_value = [resultado(16, None, "Canoas", "RS")]
    with pytest.raises(PrecisaoInsuficiente) as ex:
        d.servico().resolver_para_analise(req("100"))
    assert ex.value.latitude_aproximada == -29.92
    d.repositorio.salvar.assert_not_called()


def test_resultado_em_outra_cidade_e_descartado_e_o_endereco_nao_e_encontrado(d):
    d.nominatim.buscar_estruturado.return_value = [resultado(30, "100", "Curitiba", "PR")]
    with pytest.raises(EnderecoNaoEncontrado):
        d.servico().resolver_para_analise(req("100"))


def test_coordenadas_confirmadas_no_mapa_dispensam_a_geocodificacao(d):
    d.ibge.codigo_municipio.return_value = "4304606"
    r = EnderecoRequest(rua="Rua de Teste", numero="100", cidade="Canoas", estado="RS", latitude=-29.95, longitude=-51.17)

    e = d.servico().resolver_para_analise(r)

    assert e.precisao == PrecisaoGeocodificacao.MANUAL
    assert e.latitude == -29.95
    assert e.chave_normalizada is None
    d.nominatim.buscar_estruturado.assert_not_called()


def test_endereco_ja_geocodificado_e_reaproveitado_do_banco(d):
    existente = Endereco(precisao=PrecisaoGeocodificacao.NUMERO)
    d.repositorio.por_chave.side_effect = lambda chave: existente if chave == "rua de teste|100|canoas|RS" else None
    assert d.servico().resolver_para_analise(req("100")) is existente
    d.nominatim.buscar_estruturado.assert_not_called()


def test_falha_do_ibge_nao_impede_a_analise(d):
    d.nominatim.buscar_estruturado.return_value = [resultado(30, "100", "Canoas", "RS")]
    d.ibge.codigo_municipio.side_effect = IntegracaoExterna("IBGE", "fora do ar")
    assert d.servico().resolver_para_analise(req("100")).codigo_ibge is None


def test_nome_de_lugar_escrito_separado_tambem_e_buscado_junto(d):
    shopping = ResultadoGeocodificacao(-29.9105, -51.164, 30, "shop", "4502", "Avenida Farroupilha", "Marechal Rondon",
                                       "Canoas", "RS", None, "ParkShopping Canoas, 4502, Avenida Farroupilha, Canoas")
    d.nominatim.buscar_texto.side_effect = lambda texto, limite: (
        [shopping] if texto == "ParkShopping, Canoas - RS, Brasil" else [])

    r = d.servico().localizar(EnderecoRequest(rua="Park Shopping", cidade="Canoas", estado="RS"))

    assert r.candidatos[0].endereco_encontrado.startswith("ParkShopping Canoas")
    assert nome_junto(EnderecoRequest(rua="Rua de Teste", cidade="Canoas", estado="RS")) is None
    assert nome_junto(EnderecoRequest(rua="Shopping", cidade="Canoas", estado="RS")) is None
    assert nome_junto(EnderecoRequest(rua="Park Shopping", numero="10", cidade="Canoas", estado="RS")) is None


def test_codigo_ibge_sai_da_lista_guardada_mesmo_com_a_api_do_ibge_fora_do_ar(d):
    servico = d.servico(MunicipiosIbge.de([("4304606", "RS", "Canoas"), ("4206702", "SC", "Herval D`Oeste")]))
    manual = EnderecoRequest(rua="Rua de Teste", numero="100", cidade="canoas", estado="RS", latitude=-29.92,
                             longitude=-51.18)
    assert servico.resolver_para_analise(manual).codigo_ibge == "4304606"
    outra_grafia = EnderecoRequest(rua="Rua A", numero="1", cidade="Herval d'Oeste", estado="SC", latitude=-27.19,
                                   longitude=-51.49)
    assert servico.resolver_para_analise(outra_grafia).codigo_ibge == "4206702"
    d.ibge.codigo_municipio.assert_not_called()


def test_endereco_guardado_sem_codigo_ibge_e_completado_na_consulta_seguinte(d):
    existente = Endereco(precisao=PrecisaoGeocodificacao.NUMERO)
    d.repositorio.por_chave.side_effect = lambda chave: existente if chave == "rua de teste|100|canoas|RS" else None
    d.ibge.codigo_municipio.return_value = "4304606"
    assert d.servico().resolver_para_analise(req("100")).codigo_ibge == "4304606"
    d.repositorio.salvar.assert_called_once_with(existente)


def test_codigo_ibge_vem_do_viacep_quando_o_cep_confere_com_a_cidade(d):
    d.via_cep.buscar.side_effect = lambda cep: (DadosCep("92010-000", "Rua de Teste", "Centro", "Canoas", "RS", "4304606")
                                                if cep == "92010-000" else None)
    d.nominatim.buscar_estruturado.return_value = [resultado(30, "100", "Canoas", "RS")]
    r = EnderecoRequest(cep="92010000", rua="Rua de Teste", numero="100", cidade="Canoas", estado="RS")

    e = d.servico().resolver_para_analise(r)

    assert e.codigo_ibge == "4304606"
    assert e.cep == "92010-000"
    assert e.bairro == "Centro"
    d.ibge.codigo_municipio.assert_not_called()


def test_localizar_devolve_candidatos_e_indica_quando_a_precisao_nao_basta(d):
    d.nominatim.buscar_estruturado.return_value = [resultado(18, None, "Canoas", "RS")]
    r = d.servico().localizar(req(None))
    assert not r.candidatos[0].suficiente_para_analise
    assert r.candidatos[0].precisao == "APROXIMADA"
    assert "Clique no mapa" in r.mensagem


def test_cep_inexistente_gera_erro_explicativo(d):
    with pytest.raises(EnderecoNaoEncontrado) as ex:
        d.servico().buscar_cep("99999-999")
    d.via_cep.buscar.assert_called_once_with("99999999")
    assert "99999-999" in str(ex.value)
