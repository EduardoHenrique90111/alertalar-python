from __future__ import annotations

from dataclasses import dataclass

from alertalar.modelos.enums import CategoriaFator, ClassificacaoRisco, SituacaoFator
from alertalar.servicos.analise.contexto import ContextoAnalise
from alertalar.servicos.analise.fatores import (
    AvaliacaoFator,
    FatorElevacaoRelativa,
    FatorProximidadeAgua,
    FatorRisco,
    FatorSetorRiscoOficial,
)
from alertalar.util import numeros

VERSAO_METODOLOGIA = "1.0"
LIMIAR_ALTO = 1.9
LIMIAR_MODERADO = 1.0
FATORES_GEOGRAFICOS = frozenset({FatorProximidadeAgua.CODIGO, FatorElevacaoRelativa.CODIGO,
                                 FatorSetorRiscoOficial.CODIGO})


@dataclass(frozen=True)
class ResultadoAnalise:
    classificacao: ClassificacaoRisco
    indice: float | None
    fatores: list[AvaliacaoFator]
    justificativa: str
    versao_metodologia: str


class AnaliseRiscoService:
    def __init__(self, fatores: list[FatorRisco]):
        self.fatores = list(fatores)

    def analisar(self, contexto: ContextoAnalise) -> ResultadoAnalise:
        return self.consolidar([f.avaliar(contexto) for f in self.fatores])

    def consolidar(self, avaliacoes: list[AvaliacaoFator]) -> ResultadoAnalise:
        avaliados = [a for a in avaliacoes if a.avaliado]
        tem_geografico = any(a.codigo in FATORES_GEOGRAFICOS for a in avaliados)
        forca_alto = any(a.forca_alto for a in avaliados)
        minimo_moderado = any(a.minimo_moderado for a in avaliados)

        media = None
        if avaliados:
            media = sum(a.pontuacao * a.peso for a in avaliados) / sum(a.peso for a in avaliados)

        if forca_alto:
            classificacao = ClassificacaoRisco.ALTO
        elif len(avaliados) < 2 or not tem_geografico:
            classificacao = ClassificacaoRisco.DADOS_INSUFICIENTES
        elif media >= LIMIAR_ALTO:
            classificacao = ClassificacaoRisco.ALTO
        elif media >= LIMIAR_MODERADO:
            classificacao = ClassificacaoRisco.MODERADO
        else:
            classificacao = ClassificacaoRisco.MODERADO if minimo_moderado else ClassificacaoRisco.BAIXO

        indice = None
        if classificacao != ClassificacaoRisco.DADOS_INSUFICIENTES and media is not None:
            indice = numeros.arredondar(media / 3.0 * 1000) / 10.0
        justificativa = _justificativa(classificacao, media, avaliacoes, avaliados, forca_alto, minimo_moderado,
                                       tem_geografico)
        return ResultadoAnalise(classificacao, indice, avaliacoes, justificativa, VERSAO_METODOLOGIA)


def _justificativa(c: ClassificacaoRisco, media: float | None, todos: list[AvaliacaoFator],
                   avaliados: list[AvaliacaoFator], forca_alto: bool, minimo_moderado: bool,
                   tem_geografico: bool) -> str:
    partes = [texto_classificacao(c), "\n\n"]
    if c == ClassificacaoRisco.DADOS_INSUFICIENTES:
        if not avaliados:
            motivo = "Nenhum fator pôde ser avaliado com dados reais nesta consulta."
        elif not tem_geografico:
            motivo = "Nenhum fator geográfico (proximidade de água, elevação ou setor de risco) pôde ser avaliado."
        else:
            motivo = "Apenas um fator pôde ser avaliado, o que não é suficiente para uma classificação."
        partes.append(motivo + " As fontes indisponíveis estão listadas abaixo; tente novamente mais tarde.\n\n")
    else:
        partes.append(f"Média ponderada dos {len(avaliados)} fator(es) avaliado(s): {numeros.decimal(media, 2)} numa "
                      "escala de 0 a 3 (alto a partir de 1,9; moderado a partir de 1,0).")
        if forca_alto:
            partes.append(" O ponto está dentro de setor de risco hidrológico alto ou muito alto do SGB, o que "
                          "determina a classificação \"alto risco\".")
        elif minimo_moderado and c == ClassificacaoRisco.MODERADO and media < LIMIAR_MODERADO:
            partes.append(" Há ocorrências confirmadas repetidas nas proximidades, por isso a classificação mínima "
                          "é \"risco moderado\".")
        partes.append("\n\n")
    titulos = {CategoriaFator.RISCO_MAPEADO: "Risco mapeado por órgão oficial:",
               CategoriaFator.SUSCETIBILIDADE: "Suscetibilidade geográfica:",
               CategoriaFator.HISTORICO: "Risco histórico:"}
    for cat in CategoriaFator:
        da_categoria = [a for a in todos if a.categoria == cat]
        if not da_categoria:
            continue
        partes.append(titulos[cat] + "\n")
        partes.append("\n".join(f"- {a.nome} [{_rotulo_situacao(a)}]: {a.explicacao}" for a in da_categoria))
        partes.append("\n\n")
    partes.append("Esta avaliação indica a presença de indícios nos dados disponíveis e não é laudo técnico, estudo "
                  "hidrológico nem previsão do tempo. Situações de emergência: Defesa Civil 199 ou Bombeiros 193.")
    return "".join(partes).strip()


def _rotulo_situacao(a: AvaliacaoFator) -> str:
    if a.situacao == SituacaoFator.AVALIADO:
        return f"pontuação {a.pontuacao} de 3"
    if a.situacao == SituacaoFator.SEM_REGISTRO:
        return "sem registro, não pontua"
    return "fonte indisponível, não pontua"


def texto_classificacao(c: ClassificacaoRisco) -> str:
    return {
        ClassificacaoRisco.ALTO: "ALTO RISCO: os dados disponíveis reúnem indícios fortes de que o local é suscetível "
                                 "a enchentes ou alagamentos.",
        ClassificacaoRisco.MODERADO: "RISCO MODERADO: os dados disponíveis indicam alguns fatores de suscetibilidade a "
                                     "enchentes ou alagamentos.",
        ClassificacaoRisco.BAIXO: "BAIXO RISCO: os dados disponíveis não indicam suscetibilidade elevada neste ponto. "
                                  "Isso NÃO significa que o local esteja livre de alagamentos: chuvas extremas, falhas "
                                  "de drenagem e dados incompletos podem alterar esta avaliação.",
        ClassificacaoRisco.DADOS_INSUFICIENTES: "DADOS INSUFICIENTES: não há dados confiáveis suficientes para "
                                                "classificar este endereço.",
    }[c]
