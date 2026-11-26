from __future__ import annotations

from alertalar.esquemas import Chuva, RiscoAgora, Vazao
from alertalar.modelos.enums import ClassificacaoRisco
from alertalar.util import numeros

CRITERIO = ("Chuva medida pelos limites do INMET para avisos de chuvas intensas "
            "(20 mm/h ou 30 mm em 24 h; 30 mm/h ou 50 mm em 24 h; acima de 60 mm/h ou 100 mm em 24 h) e pelo "
            "acumulado de 72 h, combinada com a suscetibilidade do local. Dados estimados por modelos "
            "meteorológicos (Open-Meteo): não é alerta oficial.")

SUBIDA_RIO = 1.5

ROTULO_CHUVA = ("Sem chuva forte", "Chuva com perigo potencial", "Chuva forte", "Chuva muito forte")
_SUSC_FRASE = ("baixa", "moderada", "alta")


def avaliar(chuva: Chuva | None, vazao: Vazao | None, suscetibilidade: ClassificacaoRisco | None,
            perto_de_agua: bool) -> RiscoAgora:
    susc = None if suscetibilidade is None else suscetibilidade.value
    if chuva is None or not chuva.disponivel:
        return RiscoAgora(nivel="INDISPONIVEL", rotulo="Indisponível", nivel_chuva=None, nivel_chuva_rotulo=None,
                          suscetibilidade=susc,
                          resumo="Não foi possível obter os dados de chuva agora, então o risco deste momento não foi "
                                 "calculado. Acompanhe os alertas da Defesa Civil (SMS 40199).",
                          motivos=[], proximos_dias=None, criterio=CRITERIO)
    motivos: list[str] = []
    n_chuva = nivel_chuva(chuva, motivos)
    s = {ClassificacaoRisco.BAIXO: 0, ClassificacaoRisco.ALTO: 2}.get(suscetibilidade or ClassificacaoRisco.MODERADO, 1)
    risco = 0 if n_chuva == 0 else min(3, n_chuva - 1 + s)

    if (perto_de_agua and vazao is not None and vazao.disponivel and vazao.hoje_m3s is not None
            and vazao.maxima_prevista_7_dias_m3s is not None and vazao.hoje_m3s > 0
            and vazao.maxima_prevista_7_dias_m3s >= vazao.hoje_m3s * SUBIDA_RIO):
        pct = numeros.arredondar((vazao.maxima_prevista_7_dias_m3s / vazao.hoje_m3s - 1) * 100)
        motivos.append(f"O rio mais próximo na grade do modelo deve subir cerca de {pct}% nos próximos 7 dias, e o "
                       "local fica perto de água.")
        risco = max(risco, 1)

    proximos_dias = None
    if chuva.maior_24h_entre_24e72h_mm is not None and chuva.maior_24h_entre_24e72h_mm >= 50:
        proximos_dias = (f"Previsão de até {_mm(chuva.maior_24h_entre_24e72h_mm)} de chuva em 24 horas entre amanhã "
                         "e depois de amanhã: o risco pode aumentar. Volte a consultar.")
    if not motivos:
        motivos.append(f"Sem chuva forte nas últimas 24 horas nem prevista para as próximas 24 horas "
                       f"({_mm(chuva.ultimas_24h_mm)} nas últimas 24 h; {_mm(chuva.proximas_24h_mm)} previstos).")
    nomes = ("BAIXO", "ATENCAO", "ALTO", "MUITO_ALTO")
    rotulos = ("Baixo agora", "Atenção", "Alto agora", "Muito alto agora")
    return RiscoAgora(nivel=nomes[risco], rotulo=rotulos[risco], nivel_chuva=n_chuva,
                      nivel_chuva_rotulo=ROTULO_CHUVA[n_chuva], suscetibilidade=susc,
                      resumo=_resumo(risco, n_chuva, s, suscetibilidade is not None), motivos=list(motivos),
                      proximos_dias=proximos_dias, criterio=CRITERIO)


def nivel_chuva(c: Chuva, motivos: list[str]) -> int:
    nivel = 0
    hora_passada = _valor(c.maior_intensidade_horaria_ultimas_24h_mm)
    hora_futura = _valor(c.maior_intensidade_horaria_proximas_24h_mm)
    hora = max(hora_passada, hora_futura)
    por_hora = 3 if hora > 60 else 2 if hora >= 30 else 1 if hora >= 20 else 0
    if por_hora > 0:
        motivos.append(f"Chuva de até {_mm(hora)} em uma hora "
                       + ("prevista para as próximas 24 horas." if hora_futura >= hora_passada
                          else "nas últimas 24 horas."))
        nivel = por_hora
    passado = _valor(c.ultimas_24h_mm)
    futuro = _valor(c.proximas_24h_mm)
    por_dia = max(_nivel_dia(passado), _nivel_dia(futuro))
    if por_dia > 0:
        if _nivel_dia(passado) > 0:
            motivos.append(f"{_mm(passado)} de chuva nas últimas 24 horas.")
        if _nivel_dia(futuro) > 0:
            motivos.append(f"{_mm(futuro)} de chuva previstos para as próximas 24 horas.")
        nivel = max(nivel, por_dia)
    acumulado = _valor(c.ultimas_72h_mm)
    por_72h = 2 if acumulado >= 150 else 1 if acumulado >= 100 else 0
    if por_72h > 0:
        motivos.append(f"{_mm(acumulado)} de chuva nas últimas 72 horas: o solo encharcado escoa menos água.")
        nivel = max(nivel, por_72h)
    return nivel


def _nivel_dia(mm: float) -> int:
    return 3 if mm > 100 else 2 if mm >= 50 else 1 if mm >= 30 else 0


def _resumo(risco: int, n_chuva: int, suscetibilidade: int, suscetibilidade_conhecida: bool) -> str:
    local = f" num local de suscetibilidade {_SUSC_FRASE[suscetibilidade]}." if suscetibilidade_conhecida else "."
    if n_chuva == 0:
        base = "Sem chuva forte agora nem prevista para as próximas 24 horas."
        if risco > 0:
            return base + " Mas o rio próximo deve subir: acompanhe os alertas da Defesa Civil."
        if suscetibilidade == 2 and suscetibilidade_conhecida:
            return base + " Este local tende a ser atingido quando chove forte: acompanhe a previsão e os alertas."
        return base
    orientacao = {
        0: "Não há indício de alagamento agora, mas acompanhe a previsão.",
        1: "Acompanhe a previsão e os alertas da Defesa Civil e evite ruas que costumam alagar.",
        2: "Evite ruas alagadas, deixe documentos e remédios à mão e esteja pronto para ir a um local mais alto.",
    }.get(risco, "Se a água começar a subir, vá para um local alto (veja a rota segura) e, em emergência, ligue "
                 "199 ou 193.")
    return ROTULO_CHUVA[n_chuva] + local + " " + orientacao


def _valor(v: float | None) -> float:
    return 0.0 if v is None else v


def _mm(v: float | None) -> str:
    x = _valor(v)
    return (str(int(x)) if x == int(x) else numeros.decimal(x, 1, virgula=True)) + " mm"
