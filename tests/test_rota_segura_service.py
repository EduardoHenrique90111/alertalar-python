import math
import threading
from unittest.mock import ANY, Mock

import pytest

from alertalar.erros import IntegracaoExterna, RegraNegocio
from alertalar.integracoes.open_meteo import ElevacaoClient
from alertalar.integracoes.sgb import SetorRisco, SgbSetoresRiscoClient
from alertalar.integracoes.valhalla import FONTE as FONTE_VALHALLA
from alertalar.integracoes.valhalla import Instrucao, ModoRota, Rota, ValhallaClient
from alertalar.servicos import rota_segura
from alertalar.servicos.fontes import FonteDadosService
from alertalar.servicos.progresso_rota import CalculoCancelado, ProgressoRota
from alertalar.servicos.rota_segura import RotaSeguraService
from alertalar.util import geo

LAT, LON = -29.92, -51.18
DESTINO = geo.deslocar(LAT, LON, 2000, 30)


class Ctx:
    def __init__(self) -> None:
        self.elevacao = Mock(spec=ElevacaoClient)
        self.sgb = Mock(spec=SgbSetoresRiscoClient)
        self.roteador = Mock(spec=ValhallaClient)
        self.fontes = Mock(spec=FonteDadosService)
        self.servico = RotaSeguraService(self.elevacao, self.sgb, self.roteador, self.fontes)

    def elevacoes(self, partida, destino, perfil) -> None:
        def responder(pontos):
            if len(pontos) == 2:
                return [partida, destino]
            return [perfil(p) for p in pontos]
        self.elevacao.elevacoes.side_effect = responder

    def roteador_encontra(self) -> None:
        self.roteador.rota.side_effect = lambda lat, lon, lat_d, lon_d, modo, evitar: rota_ate(lat_d, lon_d)

    def calcular(self, modo: ModoRota, progresso: ProgressoRota | None = None):
        if progresso is None:
            return self.servico.calcular(LAT, LON, DESTINO[0], DESTINO[1], modo)
        return self.servico.calcular(LAT, LON, DESTINO[0], DESTINO[1], modo, progresso)


@pytest.fixture
def ctx():
    c = Ctx()
    yield c
    c.servico.encerrar()


def rota_ate(lat_d, lon_d) -> Rota:
    pontos = [(LAT, LON), ((LAT + lat_d) / 2, (LON + lon_d) / 2), (lat_d, lon_d)]
    return Rota(pontos, [Instrucao("Siga ao norte na Rua de Teste.", 300, 240, 0, 2),
                         Instrucao("Você chegou ao seu destino.", 0, 0, 2, 4)], 600, 480)


def setor(numero, lat, lon, meio_lado, hidrologico) -> SetorRisco:
    d_lat = meio_lado / 111_320.0
    d_lon = meio_lado / (111_320.0 * math.cos(math.radians(lat)))
    anel = ((lat - d_lat, lon - d_lon), (lat - d_lat, lon + d_lon), (lat + d_lat, lon + d_lon),
            (lat + d_lat, lon - d_lon), (lat - d_lat, lon - d_lon))
    return SetorRisco("Canoas", "RS", numero, "Vila Teste", "Inundação" if hidrologico else "Deslizamento",
                      "Muito Alto", None, None, hidrologico, (anel,))


def rotas_com(ctx, *, com_desvio=None, sem_desvio=None) -> None:
    def responder(lat, lon, lat_d, lon_d, modo, evitar):
        acao = com_desvio if evitar else sem_desvio
        if isinstance(acao, Exception):
            raise acao
        return rota_ate(lat_d, lon_d)
    ctx.roteador.rota.side_effect = responder


def test_rota_encontrada_com_altura_perfil_fontes_e_avisos_padrao(ctx):
    ctx.elevacoes(8.0, 15.0, lambda p: 8.0 + geo.distancia_metros(LAT, LON, p[0], p[1]) / 300)
    ctx.sgb.buscar_proximos.return_value = []
    ctx.roteador_encontra()

    r = ctx.calcular(ModoRota.A_PE)

    assert r.status == "ROTA_ENCONTRADA"
    assert r.destino.latitude == pytest.approx(DESTINO[0], abs=1e-9)
    assert r.destino.ganho_elevacao == pytest.approx(7.0)
    assert r.destino.distancia_reta_metros == pytest.approx(2000, abs=3)
    assert "7 m mais alto" in r.destino.descricao
    assert r.origem.elevacao == pytest.approx(8.0)
    assert r.trajeto.distancia_metros == 600
    assert len(r.trajeto.instrucoes) == 2
    assert r.trajeto.desvio_areas_risco_aplicado
    assert r.mensagem == "Siga por 600 m (cerca de 8 min a pé) até o destino escolhido."
    assert r.perfil is not None
    assert r.perfil.elevacao_minima == pytest.approx(8.0)
    assert any("Valhalla" in f for f in r.fontes)
    assert any("Copernicus" in f for f in r.fontes)
    assert any("não uma rota oficial" in a for a in r.avisos)
    assert any("Nunca atravesse ruas alagadas" in a for a in r.avisos)
    assert len(r.avisos) == 2, "só os avisos padrão"
    ctx.fontes.registrar_acesso.assert_any_call("VALHALLA_ROTAS", ANY)
    ctx.roteador.rota.assert_called_once_with(LAT, LON, DESTINO[0], DESTINO[1], ModoRota.A_PE, [])
    assert ctx.sgb.buscar_proximos.call_args.args[2] == 2500

    ctx.calcular(ModoRota.A_PE)
    assert ctx.roteador.rota.call_count == 1


def test_areas_de_risco_entre_a_partida_e_o_destino_vao_para_o_roteador_evitar(ctx):
    ctx.elevacoes(10.0, 10.0, lambda p: 10.0)
    meio = geo.deslocar(LAT, LON, 1000, 30)
    ao_lado = geo.deslocar(LAT, LON, 1500, 120)
    ctx.sgb.buscar_proximos.return_value = [setor("H1", meio[0], meio[1], 80, True),
                                            setor("H2", ao_lado[0], ao_lado[1], 60, True),
                                            setor("D1", meio[0], meio[1] + 0.003, 60, False)]
    ctx.roteador_encontra()

    r = ctx.calcular(ModoRota.A_PE)

    assert r.status == "ROTA_ENCONTRADA"
    assert len(r.setores_risco) == 2, "somente setores hidrológicos aparecem no mapa"
    assert r.trajeto.setores_evitados == 2
    assert len(ctx.roteador.rota.call_args.args[5]) == 2


def test_se_o_desvio_falhar_tenta_sem_desvio_e_avisa(ctx):
    ctx.elevacoes(10.0, 10.0, lambda p: 10.0)
    meio = geo.deslocar(LAT, LON, 1000, 30)
    ctx.sgb.buscar_proximos.return_value = [setor("H1", meio[0], meio[1], 80, True)]
    rotas_com(ctx, com_desvio=IntegracaoExterna(FONTE_VALHALLA, "sem caminho"))

    r = ctx.calcular(ModoRota.CARRO)

    assert r.status == "ROTA_ENCONTRADA"
    assert not r.trajeto.desvio_areas_risco_aplicado
    assert r.trajeto.setores_evitados == 0
    assert any("desvie das áreas de risco" in a for a in r.avisos)
    assert "de carro" in r.mensagem


def test_trecho_do_caminho_mais_baixo_que_a_partida_gera_aviso(ctx):
    fundo = geo.deslocar(LAT, LON, 600, 30)
    ctx.elevacoes(8.0, 9.0, lambda p: 2.0 if geo.distancia_metros(fundo[0], fundo[1], p[0], p[1]) < 60 else 9.0)
    ctx.sgb.buscar_proximos.return_value = []
    ctx.roteador.rota.side_effect = lambda lat, lon, lat_d, lon_d, modo, evitar: Rota(
        [(LAT, LON), fundo, (lat_d, lon_d)], [], 2100, 1600)

    r = ctx.calcular(ModoRota.A_PE)

    assert r.perfil.elevacao_minima == pytest.approx(2.0)
    assert any("6 m mais baixo que o ponto de partida" in a for a in r.avisos), r.avisos


def test_destino_dentro_de_area_de_risco_ou_mais_baixo_que_a_partida_gera_aviso(ctx):
    destino = geo.deslocar(LAT, LON, 800, 90)
    ctx.elevacoes(12.0, 4.0, lambda p: 8.0)
    ctx.sgb.buscar_proximos.return_value = [setor("H7", destino[0], destino[1], 100, True)]
    ctx.roteador_encontra()

    r = ctx.servico.calcular(LAT, LON, destino[0], destino[1], ModoRota.CARRO)

    assert r.status == "ROTA_ENCONTRADA"
    assert any("O destino escolhido fica dentro de uma área de risco" in a and "H7" in a
               and "prefira um lugar mais alto" in a for a in r.avisos), r.avisos
    assert any("8 m mais baixo que o ponto de partida" in a for a in r.avisos)
    assert not any("O caminho passa por dentro" in a for a in r.avisos), "setor do destino já foi avisado"
    assert not any("terreno mais alto" in a for a in r.avisos)
    assert r.destino.ganho_elevacao == pytest.approx(-8.0)


def test_partida_dentro_de_area_de_risco_avisa_primeiro_e_o_setor_nao_entra_no_desvio(ctx):
    ctx.elevacoes(4.0, 12.0, lambda p: 10.0)
    ctx.sgb.buscar_proximos.return_value = [setor("H9", LAT, LON, 400, True)]
    ctx.roteador_encontra()

    r = ctx.calcular(ModoRota.A_PE)

    assert r.status == "ROTA_ENCONTRADA"
    assert "O ponto de partida está dentro de uma área de risco" in r.avisos[0]
    assert "setor H9" in r.avisos[0]
    assert ctx.roteador.rota.call_args.args[5] == []


def test_sem_altura_o_caminho_sai_avisando_e_sem_roteador_o_destino_fica_no_mapa(ctx):
    ctx.elevacao.elevacoes.side_effect = IntegracaoExterna("Open-Meteo", "fora do ar")
    ctx.sgb.buscar_proximos.side_effect = IntegracaoExterna("SGB", "fora do ar")
    ctx.roteador_encontra()

    r = ctx.calcular(ModoRota.A_PE)

    assert r.status == "ROTA_ENCONTRADA"
    assert r.origem.elevacao is None
    assert r.destino.ganho_elevacao is None
    assert r.perfil is None
    assert r.destino.descricao.endswith("em linha reta.")
    assert "Serviço Geológico do Brasil" in r.avisos[0]
    assert rota_segura.SEM_PERFIL in r.avisos

    outro = Ctx()
    outro.elevacoes(10.0, 10.0, lambda p: 10.0)
    outro.sgb.buscar_proximos.return_value = []
    outro.roteador.rota.side_effect = IntegracaoExterna(FONTE_VALHALLA, "fora do ar")
    sem_roteador = outro.calcular(ModoRota.A_PE)
    assert sem_roteador.status == "ROTA_INDISPONIVEL"
    assert sem_roteador.destino is not None, "o destino continua marcado no mapa"
    assert sem_roteador.trajeto is None
    assert "não conseguiu traçar o caminho" in sem_roteador.mensagem
    assert outro.roteador.rota.call_count == 1
    outro.servico.encerrar()


def test_destino_longe_demais_no_mesmo_lugar_ou_fora_do_brasil_e_recusado(ctx):
    longe = geo.deslocar(LAT, LON, 25_000, 0)
    with pytest.raises(RegraNegocio) as e:
        ctx.servico.calcular(LAT, LON, longe[0], longe[1], ModoRota.CARRO)
    assert "até 20 km" in str(e.value)
    assert "25 km" in str(e.value)
    for args in ((LAT, LON, LAT + 0.0001, LON), (LAT, LON, 40.7, -74.0), (40.7, -74.0, 40.71, -74.0)):
        with pytest.raises(RegraNegocio):
            ctx.servico.calcular(*args, ModoRota.A_PE)
    ctx.roteador.rota.assert_not_called()


def test_distancias_e_tempos_em_portugues():
    assert rota_segura.formatar_distancia(247) == "250 m"
    assert rota_segura.formatar_distancia(1234) == "1,2 km"
    assert rota_segura.formatar_distancia(3000) == "3 km"
    assert rota_segura.formatar_tempo(20) == "1 min"
    assert rota_segura.formatar_tempo(3900) == "1 h 5 min"


class Avisos(ProgressoRota):
    def __init__(self) -> None:
        self.eventos = []
        self.desistiu = False
        self._trava = threading.Lock()

    def informar(self, evento) -> None:
        with self._trava:
            self.eventos.append(evento)

    def cancelado(self) -> bool:
        return self.desistiu

    def de(self, etapa):
        return [e.estado for e in self.eventos if e.etapa == etapa]

    def ultimo_detalhe(self, etapa):
        return [e.detalhe for e in self.eventos if e.etapa == etapa][-1]

    def detalhes_em_andamento(self, etapa):
        return [e.detalhe for e in self.eventos if e.etapa == etapa and e.estado == "EM_ANDAMENTO"]


def test_andamento_cada_consulta_externa_e_avisada_ao_comecar_e_ao_terminar(ctx):
    ctx.elevacoes(8.0, 15.0, lambda p: 10.0)
    meio = geo.deslocar(LAT, LON, 1000, 30)
    ctx.sgb.buscar_proximos.return_value = [setor("H1", meio[0], meio[1], 80, True)]
    ctx.roteador_encontra()
    avisos = Avisos()

    r = ctx.calcular(ModoRota.A_PE, avisos)

    assert r.status == "ROTA_ENCONTRADA"
    assert [e.etapa for e in avisos.eventos[:4]] == ["ALTURA", "SETORES", "CAMINHO", "PERFIL"]
    assert all(e.estado == "PENDENTE" for e in avisos.eventos[:4])
    for etapa in ("ALTURA", "SETORES", "CAMINHO", "PERFIL"):
        assert avisos.de(etapa) == ["PENDENTE", "EM_ANDAMENTO", "CONCLUIDA"], etapa
    assert avisos.eventos[0].rotulo == "Altura da partida e do destino"
    assert avisos.eventos[1].rotulo == "Áreas de risco no trajeto"
    assert avisos.ultimo_detalhe("ALTURA") == "2 pontos analisados"
    assert avisos.ultimo_detalhe("SETORES") == "1 área de risco de inundação encontrada"
    assert avisos.ultimo_detalhe("CAMINHO") == "600 m pelas ruas"
    assert avisos.detalhes_em_andamento("CAMINHO") == ["desviando de 1 área de risco"]
    caminho = next(e for e in avisos.eventos if e.etapa == "CAMINHO")
    assert caminho.rotulo == "Caminho pelas ruas"
    assert "Valhalla" in caminho.fonte
    assert all("SGB" in e.fonte for e in avisos.eventos if e.etapa == "SETORES")

    de_novo = Avisos()
    ctx.calcular(ModoRota.A_PE, de_novo)
    assert de_novo.eventos == []


def test_andamento_falhas_e_nova_tentativa_sem_desvio_aparecem_na_etapa_certa(ctx):
    ctx.elevacoes(10.0, 10.0, lambda p: None)
    ctx.sgb.buscar_proximos.side_effect = IntegracaoExterna("SGB", "fora do ar")
    ctx.roteador_encontra()
    avisos = Avisos()

    r = ctx.calcular(ModoRota.CARRO, avisos)

    assert r.status == "ROTA_ENCONTRADA"
    assert avisos.de("SETORES") == ["PENDENTE", "EM_ANDAMENTO", "FALHOU"]
    assert "não vai desviar" in avisos.ultimo_detalhe("SETORES")
    assert avisos.detalhes_em_andamento("CAMINHO") == ["traçando o caminho"]
    assert avisos.de("PERFIL") == ["PENDENTE", "EM_ANDAMENTO", "FALHOU"], "perfil sem altura dos pontos"
    assert rota_segura.SEM_PERFIL in r.avisos

    meio = geo.deslocar(LAT, LON, 1000, 30)
    ctx.elevacoes(10.0, 10.0, lambda p: 10.0)
    ctx.sgb.buscar_proximos.side_effect = None
    ctx.sgb.buscar_proximos.return_value = [setor("H1", meio[0], meio[1], 80, True)]
    rotas_com(ctx, com_desvio=IntegracaoExterna(FONTE_VALHALLA, "sem caminho"))
    nova_tentativa = Avisos()

    ctx.calcular(ModoRota.A_PE, nova_tentativa)

    assert nova_tentativa.de("CAMINHO") == ["PENDENTE", "EM_ANDAMENTO", "EM_ANDAMENTO", "CONCLUIDA"]
    assert nova_tentativa.detalhes_em_andamento("CAMINHO") == [
        "desviando de 1 área de risco", "nova tentativa, sem o desvio (a anterior não deu certo)"]


def test_andamento_roteador_fora_do_ar_marca_o_caminho_como_falha_sem_perfil(ctx):
    ctx.elevacoes(10.0, 10.0, lambda p: 10.0)
    ctx.sgb.buscar_proximos.return_value = []
    ctx.roteador.rota.side_effect = IntegracaoExterna(FONTE_VALHALLA, "fora do ar")
    avisos = Avisos()

    r = ctx.calcular(ModoRota.A_PE, avisos)

    assert r.status == "ROTA_INDISPONIVEL"
    assert avisos.de("CAMINHO") == ["PENDENTE", "EM_ANDAMENTO", "FALHOU"]
    assert avisos.de("PERFIL") == ["PENDENTE"], "sem caminho, não há perfil"


def test_quem_desistiu_nao_gasta_chamadas_ao_roteador(ctx):
    ctx.elevacoes(10.0, 10.0, lambda p: 10.0)
    ctx.sgb.buscar_proximos.return_value = []
    avisos = Avisos()
    avisos.desistiu = True

    with pytest.raises(CalculoCancelado):
        ctx.calcular(ModoRota.A_PE, avisos)
    ctx.roteador.rota.assert_not_called()

    ctx.roteador_encontra()
    assert ctx.calcular(ModoRota.A_PE).status == "ROTA_ENCONTRADA"


def test_uma_falha_ao_avisar_o_andamento_nao_interrompe_o_calculo(ctx):
    ctx.elevacoes(10.0, 10.0, lambda p: 10.0)
    ctx.sgb.buscar_proximos.return_value = []
    ctx.roteador_encontra()

    class TelaFechada(ProgressoRota):
        def informar(self, evento):
            raise RuntimeError("tela fechada")

    assert ctx.calcular(ModoRota.A_PE, TelaFechada()).status == "ROTA_ENCONTRADA"
