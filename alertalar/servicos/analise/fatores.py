"""Fatores independentes da análise de risco. Cada fator lê apenas os dados de que precisa no
:class:`ContextoAnalise` e devolve uma :class:`AvaliacaoFator` explicada."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from alertalar.modelos.enums import CategoriaFator, OrigemOcorrencia, SituacaoFator, TipoEvento
from alertalar.servicos.analise import proximidade_agua
from alertalar.servicos.analise.contexto import ContextoAnalise
from alertalar.util import geo
from alertalar.util import texto as txt
from alertalar.util.numeros import arredondar


@dataclass(frozen=True)
class AvaliacaoFator:
    """Resultado da avaliação de um fator.

    ``pontuacao``: 0 (sem indício) a 3 (indício forte), None se não avaliado; ``forca_alto``:
    evidência oficial suficiente para classificar como alto risco; ``minimo_moderado``: evidência
    suficiente para impedir a classificação "baixo".
    """

    codigo: str
    nome: str
    categoria: CategoriaFator
    situacao: SituacaoFator
    pontuacao: int | None
    peso: float
    valor_observado: str | None
    explicacao: str
    codigo_fonte: str
    data_referencia: datetime | None
    forca_alto: bool = False
    minimo_moderado: bool = False

    @property
    def avaliado(self) -> bool:
        return self.situacao == SituacaoFator.AVALIADO and self.pontuacao is not None


class FatorRisco:
    codigo: str
    nome: str
    categoria: CategoriaFator
    # Peso do fator na média ponderada
    peso: float
    # Código da FonteDados que sustenta o fator
    codigo_fonte: str

    def avaliar(self, ctx: ContextoAnalise) -> AvaliacaoFator:
        raise NotImplementedError

    # ---- atalhos para as implementações ----

    def avaliado(self, pontuacao: int, valor: str | None, explicacao: str, data: datetime | None,
                 forca_alto: bool = False, minimo_moderado: bool = False) -> AvaliacaoFator:
        return AvaliacaoFator(self.codigo, self.nome, self.categoria, SituacaoFator.AVALIADO, pontuacao, self.peso,
                              valor, explicacao, self.codigo_fonte, data, forca_alto, minimo_moderado)

    def sem_registro(self, valor: str | None, explicacao: str, data: datetime | None) -> AvaliacaoFator:
        return AvaliacaoFator(self.codigo, self.nome, self.categoria, SituacaoFator.SEM_REGISTRO, None, self.peso,
                              valor, explicacao, self.codigo_fonte, data)

    def indisponivel(self, explicacao: str) -> AvaliacaoFator:
        return AvaliacaoFator(self.codigo, self.nome, self.categoria, SituacaoFator.INDISPONIVEL, None, self.peso,
                              None, explicacao, self.codigo_fonte, None)


class FatorSetorRiscoOficial(FatorRisco):
    """Setores de risco hidrológico (inundação, enxurrada, alagamento) mapeados pelo Serviço
    Geológico do Brasil. Estar dentro de um setor de risco alto ou muito alto é classificado como
    alto risco."""

    CODIGO = codigo = "SETOR_RISCO_SGB"
    nome = "Área de risco mapeada pelo SGB"
    categoria = CategoriaFator.RISCO_MAPEADO
    peso = 3.0
    codigo_fonte = "SGB_SETORES_RISCO"

    def avaliar(self, ctx: ContextoAnalise) -> AvaliacaoFator:
        dado = ctx.setores_risco
        raio = ctx.parametros.raio_setores_risco_metros
        if not dado.disponivel:
            return self.indisponivel("Não foi possível consultar a base de setores de risco do SGB nesta consulta ("
                                     f"{dado.motivo_indisponibilidade}).")
        hidrologicos = [s for s in dado.valor if s.hidrologico]
        if not hidrologicos:
            return self.sem_registro(
                f"Nenhum setor hidrológico em {raio} m",
                "Nenhum setor de risco hidrológico (inundação, enxurrada ou alagamento) mapeado pelo SGB num raio de "
                f"{raio} m. O SGB mapeia setores apenas em municípios selecionados, por isso a ausência de setor não "
                "indica ausência de risco.", dado.obtido_em)

        melhor = None
        dentro = False
        menor_distancia = float("inf")
        for s in hidrologicos:
            for anel in s.aneis:
                if geo.dentro_do_poligono(ctx.latitude, ctx.longitude, anel):
                    if not dentro or grau_alto(s.grau_risco):
                        melhor = s
                    dentro = True
                    menor_distancia = 0
                elif not dentro:
                    p = geo.ponto_mais_proximo(ctx.latitude, ctx.longitude, anel)
                    if p is not None and p[2] < menor_distancia:
                        menor_distancia = p[2]
                        melhor = s
        if melhor is None:
            # setor retornado sem geometria: o próprio serviço indicou interseção com o raio
            melhor = hidrologicos[0]
            menor_distancia = raio

        identificacao = ("setor " + ("s/n" if melhor.numero_setor is None else melhor.numero_setor)
                         + ("" if melhor.grau_risco is None else ", grau de risco " + melhor.grau_risco)
                         + ("" if melhor.tipologia is None else ", " + melhor.tipologia)
                         + ("" if melhor.data_setorizacao is None else f", mapeado em {melhor.data_setorizacao.year}"))
        if dentro:
            alto = grau_alto(melhor.grau_risco)
            explicacao = ("O ponto está DENTRO de um setor de risco hidrológico mapeado pelo Serviço Geológico do "
                          f"Brasil ({identificacao})" + ("" if melhor.local is None else ", local: " + melhor.local)
                          + ". " + ("Setores de risco alto ou muito alto são áreas onde o órgão oficial identificou "
                                    "possibilidade de danos a moradias." if alto
                                    else "Considere as recomendações da Defesa Civil do município."))
            return self.avaliado(3 if alto else 2, "Dentro do " + identificacao, explicacao, dado.obtido_em,
                                 forca_alto=alto, minimo_moderado=True)
        pontos = 2 if menor_distancia <= 100 else 1
        distancia = arredondar(menor_distancia)
        explicacao = (f"Há um setor de risco hidrológico mapeado pelo SGB a cerca de {distancia} m do ponto "
                      f"({identificacao}). O ponto não está dentro do setor, mas a proximidade indica que a vizinhança "
                      "já foi identificada como área sujeita a eventos.")
        return self.avaliado(pontos, f"Setor a {distancia} m ({identificacao})", explicacao, dado.obtido_em)


def grau_alto(grau: str | None) -> bool:
    return "alto" in txt.normalizar(grau)  # "Alto" e "Muito alto" (R3/R4)


class FatorProximidadeAgua(FatorRisco):
    """Distância até rios, canais e corpos d'água (principais) e até córregos, valas e drenos
    (secundários), com base nas geometrias do OpenStreetMap."""

    CODIGO = codigo = "PROXIMIDADE_AGUA"
    nome = "Proximidade de rios, córregos e corpos d'água"
    categoria = CategoriaFator.SUSCETIBILIDADE
    peso = 2.0
    codigo_fonte = "OSM_CURSOS_AGUA"

    def avaliar(self, ctx: ContextoAnalise) -> AvaliacaoFator:
        dado = ctx.cursos_dagua
        raio = ctx.parametros.raio_cursos_agua_metros
        if not dado.disponivel:
            return self.indisponivel("Não foi possível consultar os cursos d'água do OpenStreetMap nesta consulta ("
                                     f"{dado.motivo_indisponibilidade}).")
        cursos = dado.valor
        principal = proximidade_agua.mais_proximo(ctx.latitude, ctx.longitude, cursos, lambda c: c.principal)
        secundario = proximidade_agua.mais_proximo(ctx.latitude, ctx.longitude, cursos, lambda c: not c.principal)
        if principal is None and secundario is None:
            return self.avaliado(
                0, f"Nenhum curso d'água em {raio} m",
                f"Nenhum rio, córrego, canal ou corpo d'água está mapeado no OpenStreetMap num raio de {raio} m. "
                "Observação: córregos pequenos ou canalizados podem não estar mapeados.", dado.obtido_em)

        pontuacao = max(0 if principal is None else pontuar_principal(principal.distancia_metros),
                        0 if secundario is None else pontuar_secundario(secundario.distancia_metros))
        valor = []
        explicacao = ""
        if principal is not None:
            d = arredondar(principal.distancia_metros)
            valor.append(f"{_capitalizar(principal.curso.descricao())} a {d} m")
            explicacao += (f"O ponto está sobre a área de {principal.curso.descricao()}. "
                           if principal.distancia_metros == 0
                           else f"O curso/corpo d'água principal mais próximo é {principal.curso.descricao()}, "
                                f"a cerca de {d} m. ")
        if secundario is not None:
            d = arredondar(secundario.distancia_metros)
            valor.append(f"{_capitalizar(secundario.curso.descricao())} a {d} m")
            explicacao += (f"O córrego/vala/canal de drenagem mais próximo é {secundario.curso.descricao()}, "
                           f"a cerca de {d} m. ")
        explicacao += {
            3: "Imóveis muito próximos de rios e corpos d'água estão mais expostos a cheias.",
            2: "A distância indica exposição moderada a transbordamentos.",
            1: "A distância indica exposição baixa, mas não nula, a transbordamentos.",
        }.get(pontuacao, "A distância até cursos d'água é grande o bastante para não indicar exposição direta a "
                         "transbordamentos.")
        explicacao += " Fonte: geometrias do OpenStreetMap, cuja completude varia por região."
        return self.avaliado(pontuacao, "; ".join(valor), explicacao, dado.obtido_em)


def pontuar_principal(distancia: float) -> int:
    """Rios, canais e corpos d'água."""
    if distancia <= 150:
        return 3
    if distancia <= 400:
        return 2
    if distancia <= 1000:
        return 1
    return 0


def pontuar_secundario(distancia: float) -> int:
    """Córregos, valas e drenos (menor volume, mas transbordam com chuva forte)."""
    if distancia <= 50:
        return 2
    if distancia <= 150:
        return 1
    return 0


def _capitalizar(s: str | None) -> str | None:
    return s if not s else s[0].upper() + s[1:]


class FatorElevacaoRelativa(FatorRisco):
    """Elevação relativa do terreno (Copernicus DEM GLO-90): desnível em relação ao curso d'água
    mais próximo e em relação ao entorno imediato (pontos baixos acumulam água)."""

    CODIGO = codigo = "ELEVACAO_RELATIVA"
    nome = "Elevação relativa do terreno"
    categoria = CategoriaFator.SUSCETIBILIDADE
    peso = 2.0
    codigo_fonte = "COPERNICUS_DEM"
    # Acima desta distância, o desnível até a água deixa de ser um bom indicador local
    DISTANCIA_MAXIMA_AGUA = 1000

    def avaliar(self, ctx: ContextoAnalise) -> AvaliacaoFator:
        dado = ctx.elevacao
        if not dado.disponivel or dado.valor is None or dado.valor.elevacao_ponto is None:
            return self.indisponivel("Não foi possível obter a elevação do terreno nesta consulta"
                                     + ("." if dado.motivo_indisponibilidade is None
                                        else f" ({dado.motivo_indisponibilidade})."))
        p = dado.valor
        pontos_agua = pontos_entorno = None
        valor = f"Elevação do ponto: {arredondar(p.elevacao_ponto)} m"
        explicacao = ""
        if (p.elevacao_agua is not None and p.distancia_agua_metros is not None
                and p.distancia_agua_metros <= self.DISTANCIA_MAXIMA_AGUA):
            desnivel = p.elevacao_ponto - p.elevacao_agua
            pontos_agua = pontuar_desnivel_agua(desnivel)
            valor += f"; {_desnivel_texto(desnivel)} em relação a {p.nome_agua}"
            explicacao += (f"O terreno do ponto está {_desnivel_texto(desnivel)} em relação a {p.nome_agua} "
                           f"(a {arredondar(p.distancia_agua_metros)} m). "
                           + ("Pequenos desníveis em relação à água aumentam a chance de inundação em cheias. "
                              if pontos_agua >= 2
                              else "O desnível oferece alguma proteção, mas cheias excepcionais podem superá-lo. "
                              if pontos_agua == 1 else "O desnível é grande em relação ao curso d'água. "))
        if p.media_entorno is not None and p.pontos_entorno >= 6:
            diferenca = p.elevacao_ponto - p.media_entorno
            pontos_entorno = pontuar_depressao(diferenca)
            valor += f"; {_desnivel_texto(diferenca)} da média do entorno"
            explicacao += (f"Em relação ao entorno (raio de {p.raio_entorno_metros} m), o ponto está "
                           f"{_desnivel_texto(diferenca)} da média. "
                           + ("Pontos mais baixos que a vizinhança tendem a acumular água da chuva. "
                              if pontos_entorno > 0 else "O ponto não fica em uma depressão local. "))
        if pontos_agua is None and pontos_entorno is None:
            return self.indisponivel("A elevação do ponto foi obtida, mas não havia dados suficientes do entorno nem "
                                     "curso d'água próximo para calcular a elevação relativa.")
        pontuacao = max(pontos_agua or 0, pontos_entorno or 0)
        explicacao += ("Fonte: Copernicus DEM GLO-90 (resolução de 90 m); a precisão vertical é de alguns metros e o "
                       "modelo pode incluir altura de construções e vegetação.")
        return self.avaliado(pontuacao, valor, explicacao, dado.obtido_em)


def pontuar_desnivel_agua(desnivel: float) -> int:
    if desnivel <= 2:
        return 3
    if desnivel <= 5:
        return 2
    if desnivel <= 10:
        return 1
    return 0


def pontuar_depressao(diferenca: float) -> int:
    if diferenca <= -5:
        return 2
    if diferenca <= -2:
        return 1
    return 0


def _desnivel_texto(d: float) -> str:
    m = arredondar(abs(d))
    if m == 0:
        return "praticamente no mesmo nível"
    return f"{m} m " + ("acima" if d > 0 else "abaixo")


class FatorOcorrenciasLocais(FatorRisco):
    """Ocorrências pontuais CONFIRMADAS perto do endereço: registros oficiais com coordenadas e
    relatos de usuários já validados pela moderação. Relatos pendentes nunca entram."""

    CODIGO = codigo = "OCORRENCIAS_LOCAIS"
    nome = "Ocorrências registradas nas proximidades"
    categoria = CategoriaFator.HISTORICO
    peso = 2.0
    codigo_fonte = "ALERTALAR_RELATOS"

    def avaliar(self, ctx: ContextoAnalise) -> AvaliacaoFator:
        dado = ctx.ocorrencias_proximas
        raio = ctx.parametros.raio_ocorrencias_metros
        anos = ctx.parametros.anos_historico
        if not dado.disponivel:
            return self.indisponivel(
                f"Não foi possível consultar as ocorrências registradas ({dado.motivo_indisponibilidade}).")
        lista = dado.valor
        if not lista:
            return self.sem_registro(
                f"Nenhuma ocorrência confirmada em {raio} m",
                f"Não há ocorrências confirmadas registradas no AlertaLar num raio de {raio} m nos últimos {anos} "
                "anos. A base depende de registros oficiais com localização e de relatos validados; a ausência de "
                "registros não indica ausência de risco.", dado.obtido_em)
        oficiais = sum(1 for o in lista if o.ocorrencia.origem == OrigemOcorrencia.OFICIAL)
        relatos = len(lista) - oficiais
        mais_proxima = arredondar(min(o.distancia_metros for o in lista))
        n = len(lista)
        valor = (f"{n}" + (" ocorrência confirmada" if n == 1 else " ocorrências confirmadas")
                 + f" em {raio} m (mais próxima a {mais_proxima} m)")
        explicacao = (f"Foram encontradas {n} ocorrência(s) de alagamento/enchente confirmada(s) num raio de {raio} m "
                      f"nos últimos {anos} anos: {oficiais} registro(s) oficial(is) e {relatos} relato(s) de usuários "
                      f"validado(s). A mais próxima fica a cerca de {mais_proxima} m. "
                      + ("Ocorrências repetidas na vizinhança indicam histórico consistente de alagamentos." if n >= 3
                         else "Ocorrências na vizinhança indicam que a área já foi afetada."))
        return self.avaliado(min(n, 3), valor, explicacao, dado.obtido_em, minimo_moderado=n >= 3)


class FatorHistoricoMunicipal(FatorRisco):
    """Registros oficiais de desastres ligados a chuva no MUNICÍPIO (Atlas Digital / S2iD):
    inundações, enxurradas, alagamentos e chuvas intensas. Como não indicam a rua afetada, têm
    peso baixo e pontuação máxima 2."""

    CODIGO = codigo = "HISTORICO_MUNICIPAL"
    nome = "Histórico oficial de desastres no município"
    categoria = CategoriaFator.HISTORICO
    peso = 0.75
    codigo_fonte = "S2ID_RECONHECIMENTOS"

    def avaliar(self, ctx: ContextoAnalise) -> AvaliacaoFator:
        if txt.vazio(ctx.codigo_ibge):
            return self.indisponivel(
                "Não foi possível identificar o município (código IBGE) pelo nome da cidade informado, então os "
                "registros municipais não foram consultados. Confira o nome da cidade e faça uma nova consulta.")
        dado = ctx.historico_municipal
        if not dado.disponivel:
            return self.indisponivel(f"Não foi possível consultar o histórico municipal ({dado.motivo_indisponibilidade}).")
        h = dado.valor
        anos = ctx.parametros.anos_historico
        if not h.base_importada_para_uf:
            return self.indisponivel(f"Não há registros oficiais do Atlas Digital/S2iD carregados para {ctx.uf}. "
                                     "Sem essa base, o histórico municipal não é avaliado.")
        registros = h.registros
        n = len(registros)
        if n == 0:
            return self.avaliado(
                0, f"Nenhum registro oficial em {anos} anos",
                "Não constam registros oficiais de inundação, enxurrada, alagamento ou chuvas intensas para o município "
                f"nos últimos {anos} anos na base importada.", dado.obtido_em)
        anos_com_evento = ", ".join(list(dict.fromkeys(str(o.data_ocorrencia.year) for o in registros))[:8])
        por_tipo = Counter(o.tipo_evento for o in registros)
        detalhamento = ", ".join(f"{por_tipo[t]} {_rotulo_plural(t, por_tipo[t])}" for t in TipoEvento if t in por_tipo)
        reconhecidos = sum(1 for o in registros if o.descricao and "reconhecida pela União" in o.descricao)
        explicacao = (f"O município tem {n} registro(s) oficial(is) de desastres ligados a chuva nos últimos {anos} anos "
                      f"({detalhamento})"
                      + (f", {reconhecidos} com situação de emergência ou calamidade reconhecida pela União"
                         if reconhecidos > 0 else "")
                      + f". Anos mais recentes: {anos_com_evento}. São registros de âmbito municipal: mostram que a "
                        "cidade é atingida por esses eventos, mas não que este endereço específico foi afetado.")
        return self.avaliado(2 if n >= 5 else 1,
                             f"{n} registro(s) oficial(is) no município desde {date.today().year - anos}",
                             explicacao, dado.obtido_em)


def _rotulo_plural(tipo: TipoEvento, n: int) -> str:
    um = n == 1
    return {
        TipoEvento.INUNDACAO: "inundação" if um else "inundações",
        TipoEvento.ENXURRADA: "enxurrada" if um else "enxurradas",
        TipoEvento.ALAGAMENTO: "alagamento" if um else "alagamentos",
        TipoEvento.CHUVA_INTENSA: "registro de chuvas intensas" if um else "registros de chuvas intensas",
        TipoEvento.OUTRO: "outro evento" if um else "outros eventos",
    }[tipo]


def fatores_padrao() -> list[FatorRisco]:
    """Os fatores na ordem em que aparecem na análise."""
    return [FatorSetorRiscoOficial(), FatorProximidadeAgua(), FatorElevacaoRelativa(), FatorOcorrenciasLocais(),
            FatorHistoricoMunicipal()]
