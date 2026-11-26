import pytest

from alertalar.esquemas import Chuva, Vazao
from alertalar.modelos.enums import ClassificacaoRisco
from alertalar.servicos.analise import risco_agora


def chuva(p24, p72, hora_p, f24, hora_f, dias2e3) -> Chuva:
    return Chuva(disponivel=True, motivo=None, ultimas_24h_mm=p24, ultimas_72h_mm=p72,
                 maior_intensidade_horaria_ultimas_24h_mm=hora_p, proximas_24h_mm=f24, proximas_72h_mm=f24 + dias2e3,
                 maior_intensidade_horaria_proximas_24h_mm=hora_f, maior_24h_entre_24e72h_mm=dias2e3, fonte="teste")


def vazao(disponivel, hoje=None, sete=None, maxima=None) -> Vazao:
    return Vazao(disponivel=disponivel, motivo=None if disponivel else "sem rio", hoje_m3s=hoje,
                 sete_dias_atras_m3s=sete, maxima_prevista_7_dias_m3s=maxima,
                 tendencia="SUBINDO" if disponivel else None, fonte="teste", observacao="")


SEM_RIO = vazao(False)


def test_sem_chuva_o_risco_agora_e_baixo_mesmo_em_local_de_alta_suscetibilidade():
    r = risco_agora.avaliar(chuva(0, 0, 0, 0.4, 0.2, 0), SEM_RIO, ClassificacaoRisco.ALTO, True)
    assert (r.nivel, r.rotulo, r.nivel_chuva) == ("BAIXO", "Baixo agora", 0)
    assert "tende a ser atingido quando chove forte" in r.resumo
    assert r.motivos[0].startswith("Sem chuva forte")
    assert "(0 mm nas últimas 24 h; 0,4 mm previstos)" in r.motivos[0]
    assert r.proximos_dias is None


@pytest.mark.parametrize("descricao,p24,p72,hora_p,f24,hora_f,esperado", [
    ("garoa", 5, 8, 1, 3, 1, 0),
    ("29 mm em 24 h", 29, 29, 4, 0, 0, 0),
    ("30 mm em 24 h (piso)", 30, 30, 4, 0, 0, 1),
    ("20 mm em 1 h previsto", 0, 0, 0, 22, 20, 1),
    ("50 mm previstos em 24 h", 0, 0, 0, 50, 8, 2),
    ("30 mm em 1 h", 35, 35, 30, 0, 0, 2),
    ("100 mm em 24 h ainda é 2", 100, 100, 10, 0, 0, 2),
    ("mais de 100 mm em 24 h", 101, 101, 10, 0, 0, 3),
    ("mais de 60 mm em 1 h", 61, 61, 61, 0, 0, 3),
    ("100 mm em 72 h", 10, 100, 2, 0, 0, 1),
    ("150 mm em 72 h", 10, 150, 2, 0, 0, 2),
])
def test_nivel_da_chuva(descricao, p24, p72, hora_p, f24, hora_f, esperado):
    assert risco_agora.nivel_chuva(chuva(p24, p72, hora_p, f24, hora_f, 0), []) == esperado, descricao


@pytest.mark.parametrize("nivel,susc,esperado", [
    (1, ClassificacaoRisco.BAIXO, "BAIXO"),
    (1, ClassificacaoRisco.MODERADO, "ATENCAO"),
    (1, ClassificacaoRisco.ALTO, "ALTO"),
    (2, ClassificacaoRisco.BAIXO, "ATENCAO"),
    (2, ClassificacaoRisco.MODERADO, "ALTO"),
    (2, ClassificacaoRisco.ALTO, "MUITO_ALTO"),
    (3, ClassificacaoRisco.BAIXO, "ALTO"),
    (3, ClassificacaoRisco.MODERADO, "MUITO_ALTO"),
    (3, ClassificacaoRisco.ALTO, "MUITO_ALTO"),
    (2, ClassificacaoRisco.DADOS_INSUFICIENTES, "ALTO"),
])
def test_combinacao_da_chuva_com_a_suscetibilidade(nivel, susc, esperado):
    por_nivel = (0, 35, 60, 120)
    r = risco_agora.avaliar(chuva(por_nivel[nivel], por_nivel[nivel], 5, 0, 0, 0), SEM_RIO, susc, False)
    assert r.nivel_chuva == nivel
    assert r.nivel == esperado
    assert r.suscetibilidade == susc.value


def test_sem_consulta_a_suscetibilidade_e_tratada_como_moderada():
    r = risco_agora.avaliar(chuva(55, 55, 9, 0, 0, 0), SEM_RIO, None, False)
    assert r.nivel == "ALTO"
    assert r.suscetibilidade is None
    assert "55 mm de chuva nas últimas 24 horas." in r.motivos


def test_rio_proximo_com_previsao_de_subir_50_por_cento_leva_pelo_menos_a_atencao():
    subindo = vazao(True, 100.0, 90.0, 160.0)
    perto = risco_agora.avaliar(chuva(0, 0, 0, 0, 0, 0), subindo, ClassificacaoRisco.BAIXO, True)
    assert perto.nivel == "ATENCAO"
    assert "subir cerca de 60%" in perto.motivos[0]
    longe = risco_agora.avaliar(chuva(0, 0, 0, 0, 0, 0), subindo, ClassificacaoRisco.BAIXO, False)
    assert longe.nivel == "BAIXO"
    pouca_subida = vazao(True, 100.0, 90.0, 140.0)
    assert risco_agora.avaliar(chuva(0, 0, 0, 0, 0, 0), pouca_subida, ClassificacaoRisco.ALTO, True).nivel == "BAIXO"


def test_chuva_forte_prevista_para_depois_de_amanha_aparece_como_aviso():
    r = risco_agora.avaliar(chuva(0, 0, 0, 2, 1, 72.5), SEM_RIO, ClassificacaoRisco.MODERADO, False)
    assert r.nivel == "BAIXO"
    assert "72,5 mm" in r.proximos_dias


def test_sem_dados_de_chuva_o_risco_agora_fica_indisponivel_e_nunca_vira_baixo():
    r = risco_agora.avaliar(Chuva.indisponivel("fora do ar", "teste"), SEM_RIO, ClassificacaoRisco.ALTO, True)
    assert r.nivel == "INDISPONIVEL"
    assert r.nivel_chuva is None
    assert "40199" in r.resumo
