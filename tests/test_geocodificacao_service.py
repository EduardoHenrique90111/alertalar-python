"""Busca de endereços com o Nominatim e a reserva Photon (pausa no limite, cache, conferência de nome)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, Mock

import pytest

from alertalar.erros import IntegracaoExterna
from alertalar.esquemas import EnderecoRequest
from alertalar.integracoes import nominatim as nominatim_mod
from alertalar.integracoes import photon as photon_mod
from alertalar.integracoes.nominatim import NominatimClient, ResultadoGeocodificacao
from alertalar.integracoes.photon import PhotonClient
from alertalar.servicos import geocodificacao
from alertalar.servicos.fontes import FonteDadosService
from alertalar.servicos.geocodificacao import GeocodificacaoService


class Relogio:
    """Relógio que o teste avança."""

    def __init__(self) -> None:
        self.agora = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.agora


def sem_filtro(lista):
    return lista


def req(numero):
    return EnderecoRequest(rua="Rua de Teste", numero=numero, cidade="Canoas", estado="RS")


def casa(numero, rua):
    return ResultadoGeocodificacao(-29.92, -51.18, 30, "house", numero, rua, "Centro", "Canoas", "RS", None,
                                   f"{numero}, {rua}, Centro, Canoas, Rio Grande do Sul, Brasil")


def recusa(status: int, retry_after: float | None = None) -> IntegracaoExterna:
    return IntegracaoExterna(nominatim_mod.FONTE, "A fonte Nominatim (OpenStreetMap) não atendeu a solicitação.",
                             status_http=status, espera_pedida=retry_after)


@pytest.fixture
def ctx():
    class Ctx:
        nominatim = Mock(spec=NominatimClient)
        photon = Mock(spec=PhotonClient)
        fontes = Mock(spec=FonteDadosService)
        relogio = Relogio()
    c = Ctx()
    c.nominatim.buscar_estruturado.return_value = []
    c.nominatim.buscar_texto.return_value = []
    c.photon.buscar.return_value = []
    c.servico = GeocodificacaoService(c.nominatim, c.photon, c.fontes, c.relogio)
    return c


def test_nominatim_no_limite_a_busca_segue_no_photon_e_ele_fica_5_min_em_pausa(ctx):
    ctx.nominatim.buscar_estruturado.side_effect = recusa(429)
    ctx.photon.buscar.side_effect = lambda q, limite: [casa("200" if "200" in q else "100", "Rua de Teste")]

    busca = ctx.servico.buscar(req("100"), sem_filtro)

    assert busca.fonte == photon_mod.FONTE
    assert busca.resultados[0].numero == "100"
    ctx.photon.buscar.assert_any_call("Rua de Teste 100, Canoas, Rio Grande do Sul", ANY)
    ctx.fontes.registrar_acesso.assert_any_call("PHOTON", ANY)
    assert ctx.servico.nominatim_em_pausa()

    # Em pausa: o próximo endereço vai direto ao Photon, sem insistir no Nominatim
    assert ctx.servico.buscar(req("200"), sem_filtro).fonte == photon_mod.FONTE
    assert ctx.nominatim.buscar_estruturado.call_count == 1

    # Passados 5 minutos, o Nominatim volta a ser o primeiro
    ctx.relogio.agora += timedelta(minutes=5, seconds=1)
    assert not ctx.servico.nominatim_em_pausa()
    ctx.servico.buscar(req("300"), sem_filtro)
    assert ctx.nominatim.buscar_estruturado.call_count == 2


def test_tempo_de_pausa_pedido_pela_fonte_bloqueio_e_falhas_passageiras():
    pausa = geocodificacao.pausa
    assert pausa(recusa(429)) == timedelta(minutes=5)
    assert pausa(recusa(429, 120)) == timedelta(seconds=120)
    assert pausa(recusa(429, 5)) == timedelta(minutes=1), "mínimo de 1 min"
    assert pausa(recusa(429, 86400)) == timedelta(minutes=30), "máximo de 30 min"
    assert pausa(recusa(403)) == timedelta(minutes=30)
    assert pausa(IntegracaoExterna("N", "erro", status_http=502)) == timedelta(minutes=1)
    assert pausa(IntegracaoExterna("N", "sem resposta")) == timedelta(minutes=1)


def test_os_dois_fora_do_ar_mensagem_clara_com_a_opcao_de_marcar_no_mapa(ctx):
    ctx.nominatim.buscar_estruturado.side_effect = recusa(429)
    ctx.photon.buscar.side_effect = IntegracaoExterna(photon_mod.FONTE, "fora do ar")

    with pytest.raises(IntegracaoExterna) as e:
        ctx.servico.buscar(req("100"), sem_filtro)

    assert str(e.value) == geocodificacao.MENSAGEM_INDISPONIVEL
    assert "marque a posição direto no mapa" in str(e.value)


def test_em_pausa_se_o_photon_tambem_falhar_o_nominatim_ainda_e_tentado(ctx):
    ctx.nominatim.buscar_estruturado.side_effect = [recusa(429), [casa("200", "Rua de Teste")]]
    ctx.photon.buscar.side_effect = [[casa("100", "Rua de Teste")], IntegracaoExterna(photon_mod.FONTE, "fora do ar")]
    ctx.servico.buscar(req("100"), sem_filtro)  # põe o Nominatim em pausa

    busca = ctx.servico.buscar(req("200"), sem_filtro)

    assert busca.fonte == nominatim_mod.FONTE
    assert not ctx.servico.nominatim_em_pausa(), "respondeu de novo: sai da pausa"


def test_nominatim_nao_acha_o_photon_tenta_e_nome_diferente_vale_so_como_aproximado(ctx):
    ctx.photon.buscar.return_value = [casa("100", "Rua das Palmeiras")]

    busca = ctx.servico.buscar(req("100"), sem_filtro)

    assert busca.fonte == photon_mod.FONTE
    assert busca.resultados[0].place_rank == 20, "outra rua: só posição aproximada"
    assert not ctx.servico.nominatim_em_pausa(), "não achar não é falha"
    ctx.nominatim.buscar_texto.assert_called()  # as tentativas do Nominatim continuam iguais


def test_nominatim_nao_acha_e_o_photon_cai_endereco_nao_encontrado(ctx):
    ctx.photon.buscar.side_effect = IntegracaoExterna(photon_mod.FONTE, "fora do ar")

    busca = ctx.servico.buscar(req("100"), sem_filtro)

    assert busca.resultados == []
    assert busca.fonte == nominatim_mod.FONTE


def test_endereco_encontrado_fica_em_memoria(ctx):
    ctx.nominatim.buscar_estruturado.return_value = [casa("100", "Rua de Teste")]

    ctx.servico.buscar(req("100"), sem_filtro)
    de_novo = ctx.servico.buscar(EnderecoRequest(rua=" rua de teste ", numero="100", cidade="CANOAS", estado="rs"),
                                 sem_filtro)

    assert de_novo.fonte == nominatim_mod.FONTE
    assert ctx.nominatim.buscar_estruturado.call_count == 1
    ctx.photon.buscar.assert_not_called()


def test_conferencia_do_nome_no_resultado_aproximado_do_photon():
    assert geocodificacao.nome_confere("Av. Guilherme Schell", "6750, Avenida Guilherme Schell, Centro, Canoas")
    assert geocodificacao.nome_confere("Park Shopping", "ParkShopping Canoas, 4502, Avenida Farroupilha")
    assert geocodificacao.nome_confere("Rua São José", "Rua Sao Jose, Centro")
    assert not geocodificacao.nome_confere("Rua das Flores", "Rua das Palmeiras, Centro")
    rua = ResultadoGeocodificacao(-29.9, -51.1, 26, "residential", None, "Rua das Flores", None, "Canoas", "RS", None,
                                  "Rua das Flores, Canoas")
    assert geocodificacao.conferir_nome(rua, "R. das Flores").place_rank == 26
