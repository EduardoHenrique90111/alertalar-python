"""Cada fator é uma regra independente, testada isoladamente."""

from alertalar.modelos.enums import SituacaoFator, TipoEvento
from alertalar.servicos.analise.fatores import (
    FatorElevacaoRelativa,
    FatorHistoricoMunicipal,
    FatorOcorrenciasLocais,
    FatorProximidadeAgua,
    FatorSetorRiscoOficial,
)
from tests.apoio.contexto import ContextoTeste


class TestProximidadeAgua:
    fator = FatorProximidadeAgua()

    def test_rio_muito_proximo_pontua_tres(self):
        a = self.fator.avaliar(ContextoTeste.novo().rio_a(100).construir())
        assert a.situacao == SituacaoFator.AVALIADO
        assert a.pontuacao == 3
        assert "Rio Teste" in a.valor_observado

    def test_faixas_de_distancia(self):
        assert self.fator.avaliar(ContextoTeste.novo().rio_a(300).construir()).pontuacao == 2
        assert self.fator.avaliar(ContextoTeste.novo().rio_a(900).construir()).pontuacao == 1
        assert self.fator.avaliar(ContextoTeste.novo().rio_a(1400).construir()).pontuacao == 0

    def test_corrego_proximo_pontua_ate_dois(self):
        assert self.fator.avaliar(ContextoTeste.novo().sem_cursos_dagua().corrego_a(30).construir()).pontuacao == 2

    def test_sem_agua_no_raio_pontua_zero_com_aviso_de_completude(self):
        a = self.fator.avaliar(ContextoTeste.novo().sem_cursos_dagua().construir())
        assert a.pontuacao == 0
        assert "podem não estar mapeados" in a.explicacao

    def test_fonte_indisponivel_nao_pontua(self):
        a = self.fator.avaliar(ContextoTeste.novo().construir())
        assert a.situacao == SituacaoFator.INDISPONIVEL
        assert a.pontuacao is None

    def test_rio_e_corrego_aparecem_juntos_no_valor_observado(self):
        a = self.fator.avaliar(ContextoTeste.novo().rio_a(300).corrego_a(30).construir())
        assert a.valor_observado == "Rio Rio Teste a 300 m; Córrego/arroio Arroio Teste a 30 m"
        assert a.pontuacao == 2


class TestElevacao:
    fator = FatorElevacaoRelativa()

    def test_quase_no_nivel_da_agua_pontua_tres(self):
        assert self.fator.avaliar(ContextoTeste.novo().elevacao(5.0, 4.0, 200.0, 6.0).construir()).pontuacao == 3

    def test_terreno_alto_nao_pontua(self):
        assert self.fator.avaliar(ContextoTeste.novo().elevacao(40.0, 5.0, 200.0, 38.0).construir()).pontuacao == 0

    def test_depressao_local_pontua_mesmo_longe_da_agua(self):
        a = self.fator.avaliar(ContextoTeste.novo().elevacao(20.0, None, None, 26.0).construir())
        assert a.pontuacao == 2
        assert "acumular água" in a.explicacao

    def test_agua_distante_demais_nao_e_usada_como_referencia(self):
        assert self.fator.avaliar(ContextoTeste.novo().elevacao(10.0, 9.5, 1400.0, 10.0).construir()).pontuacao == 0

    def test_sem_elevacao_fica_indisponivel(self):
        assert self.fator.avaliar(ContextoTeste.novo().construir()).situacao == SituacaoFator.INDISPONIVEL


class TestSetores:
    fator = FatorSetorRiscoOficial()

    def test_dentro_de_setor_muito_alto_forca_alto_risco(self):
        a = self.fator.avaliar(ContextoTeste.novo().setor("Muito alto", 0, True).construir())
        assert a.pontuacao == 3
        assert a.forca_alto
        assert "DENTRO" in a.explicacao

    def test_setor_proximo_pontua_sem_forcar(self):
        # centro deslocado ~0,0025° (≈240 m); borda a ~140 m do ponto
        a = self.fator.avaliar(ContextoTeste.novo().setor("Alto", 0.0025, True).construir())
        assert a.pontuacao == 1
        assert not a.forca_alto

    def test_setor_de_deslizamento_nao_conta(self):
        a = self.fator.avaliar(ContextoTeste.novo().setor("Muito alto", 0, False).construir())
        assert a.situacao == SituacaoFator.SEM_REGISTRO

    def test_ausencia_de_setor_nao_e_evidencia_de_baixo_risco(self):
        a = self.fator.avaliar(ContextoTeste.novo().sem_setores().construir())
        assert a.situacao == SituacaoFator.SEM_REGISTRO
        assert a.pontuacao is None
        assert "não indica ausência de risco" in a.explicacao


class TestOcorrencias:
    fator = FatorOcorrenciasLocais()

    def test_tres_ou_mais_impedem_baixo_risco(self):
        a = self.fator.avaliar(ContextoTeste.novo().ocorrencias(4, 120).construir())
        assert a.pontuacao == 3
        assert a.minimo_moderado

    def test_uma_ocorrencia_pontua_um(self):
        assert self.fator.avaliar(ContextoTeste.novo().ocorrencias(1, 300).construir()).pontuacao == 1

    def test_sem_ocorrencias_nao_pontua(self):
        assert self.fator.avaliar(ContextoTeste.novo().construir()).situacao == SituacaoFator.SEM_REGISTRO


class TestHistoricoMunicipal:
    fator = FatorHistoricoMunicipal()

    def test_base_nao_importada_fica_indisponivel(self):
        a = self.fator.avaliar(ContextoTeste.novo().historico_municipal(0, False).construir())
        assert a.situacao == SituacaoFator.INDISPONIVEL

    def test_muitos_registros_pontuam_no_maximo_dois(self):
        a = self.fator.avaliar(ContextoTeste.novo().historico_municipal(12, True).construir())
        assert a.pontuacao == 2
        assert "não que este endereço" in a.explicacao

    def test_chuvas_intensas_contam_e_o_resumo_detalha_os_tipos(self):
        def ajustar(registros):
            registros[0].tipo_evento = TipoEvento.CHUVA_INTENSA
            registros[0].descricao = ("Chuvas intensas registradas pelo município. Situação de emergência ou "
                                      "calamidade reconhecida pela União.")
            registros[1].tipo_evento = TipoEvento.INUNDACAO

        a = self.fator.avaliar(ContextoTeste.novo().historico_municipal(3, True).construir(ajustar))
        assert a.pontuacao == 1
        assert "1 inundação" in a.explicacao
        assert "1 alagamento" in a.explicacao
        assert "1 registro de chuvas intensas" in a.explicacao
        assert "1 com situação de emergência ou calamidade reconhecida pela União" in a.explicacao

    def test_base_importada_sem_registros_pontua_zero(self):
        assert self.fator.avaliar(ContextoTeste.novo().historico_municipal(0, True).construir()).pontuacao == 0

    def test_sem_codigo_ibge_fica_indisponivel(self):
        a = self.fator.avaliar(ContextoTeste.novo().sem_codigo_ibge().historico_municipal(3, True).construir())
        assert a.situacao == SituacaoFator.INDISPONIVEL
