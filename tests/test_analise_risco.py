"""Classificação de risco consolidada a partir dos fatores reais."""

from alertalar.modelos.enums import ClassificacaoRisco
from alertalar.servicos.analise.analise_risco import AnaliseRiscoService
from alertalar.servicos.analise.fatores import fatores_padrao
from tests.apoio.contexto import ContextoTeste

servico = AnaliseRiscoService(fatores_padrao())


def test_terreno_baixo_junto_a_rio_com_historico_municipal_resulta_em_alto_risco():
    r = servico.analisar(ContextoTeste.novo().rio_a(120).elevacao(4.0, 3.0, 120.0, 6.0).sem_setores()
                         .historico_municipal(8, True).construir())
    assert r.classificacao == ClassificacaoRisco.ALTO
    assert r.indice is not None and r.indice >= 63


def test_ponto_alto_longe_de_agua_resulta_em_baixo_risco_com_ressalva():
    r = servico.analisar(ContextoTeste.novo().sem_cursos_dagua().elevacao(60.0, None, None, 58.0).sem_setores()
                         .historico_municipal(1, True).construir())
    assert r.classificacao == ClassificacaoRisco.BAIXO
    assert "NÃO significa que o local esteja livre" in r.justificativa


def test_fatores_intermediarios_resultam_em_risco_moderado():
    r = servico.analisar(ContextoTeste.novo().rio_a(350).elevacao(12.0, 5.0, 350.0, 12.0).sem_setores().construir())
    # proximidade 2, elevação 1 (desnível 7 m) → média 1,5
    assert r.classificacao == ClassificacaoRisco.MODERADO
    assert "Média ponderada dos 2 fator(es) avaliado(s): 1.50 numa escala de 0 a 3" in r.justificativa


def test_sem_nenhuma_fonte_disponivel_a_classificacao_e_dados_insuficientes():
    r = servico.analisar(ContextoTeste.novo().construir())
    assert r.classificacao == ClassificacaoRisco.DADOS_INSUFICIENTES
    assert r.indice is None


def test_so_historico_municipal_sem_fator_geografico_nao_basta():
    r = servico.analisar(ContextoTeste.novo().historico_municipal(10, True).ocorrencias(1, 100).construir())
    assert r.classificacao == ClassificacaoRisco.DADOS_INSUFICIENTES


def test_dentro_de_setor_muito_alto_do_sgb_e_alto_risco_mesmo_com_fontes_fora_do_ar():
    r = servico.analisar(ContextoTeste.novo().setor("Muito alto", 0, True).construir())
    assert r.classificacao == ClassificacaoRisco.ALTO
    assert "SGB" in r.justificativa


def test_tres_ocorrencias_confirmadas_impedem_baixo_risco():
    r = servico.analisar(ContextoTeste.novo().sem_cursos_dagua().elevacao(60.0, None, None, 58.0)
                         .ocorrencias(3, 200).construir())
    # média: (0*2 + 0*2 + 3*2) / 6 = 1,0 → já moderado; o mínimo garante que não seja baixo
    assert r.classificacao != ClassificacaoRisco.BAIXO


def test_a_justificativa_separa_risco_mapeado_suscetibilidade_e_historico():
    r = servico.analisar(ContextoTeste.novo().rio_a(120).elevacao(4.0, 3.0, 120.0, 6.0).construir())
    for trecho in ("Risco mapeado por órgão oficial", "Suscetibilidade geográfica", "Risco histórico",
                   "não é laudo técnico"):
        assert trecho in r.justificativa
    assert len(r.fatores) == 5
