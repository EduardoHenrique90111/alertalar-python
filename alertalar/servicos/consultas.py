from __future__ import annotations

import json
import uuid

from alertalar.erros import RecursoNaoEncontrado
from alertalar.esquemas import (
    ConsultaResponse,
    ConsultaResumo,
    DimensaoResponse,
    EnderecoRequest,
    HistoricoMunicipalResponse,
)
from alertalar.modelos.entidades import Consulta, Endereco, FatorConsulta, Usuario
from alertalar.modelos.enums import CategoriaFator, PrecisaoGeocodificacao, SituacaoFator
from alertalar.repositorios import ConsultaRepositorio
from alertalar.servicos import conversores
from alertalar.servicos.analise import proximidade_agua
from alertalar.servicos.analise.analise_risco import AnaliseRiscoService, texto_classificacao
from alertalar.servicos.analise.contexto import ContextoAnalise
from alertalar.servicos.coleta import ColetaDadosService
from alertalar.servicos.enderecos import EnderecoService
from alertalar.servicos.fontes import FonteDadosService
from alertalar.util import geo
from alertalar.util.numeros import arredondar, casas

MAX_CURSOS_NO_MAPA = 12


class ConsultaService:
    def __init__(self, enderecos: EnderecoService, coleta: ColetaDadosService, analise: AnaliseRiscoService,
                 consultas: ConsultaRepositorio, fontes: FonteDadosService):
        self.enderecos = enderecos
        self.coleta = coleta
        self.analise = analise
        self.consultas = consultas
        self.fontes = fontes

    def realizar(self, request: EnderecoRequest, usuario: Usuario | None) -> uuid.UUID:
        endereco = self.enderecos.resolver_para_analise(request)
        contexto = self.coleta.coletar(endereco)
        resultado = self.analise.analisar(contexto)

        consulta = Consulta(id=uuid.uuid4(), endereco_id=endereco.id, usuario_id=None if usuario is None else usuario.id,
                            classificacao=resultado.classificacao, indice=resultado.indice,
                            justificativa=resultado.justificativa, versao_metodologia=resultado.versao_metodologia,
                            dados_mapa=self.montar_dados_mapa(contexto))
        fontes_por_codigo = {f.codigo: f for f in self.fontes.listar()}
        for ordem, a in enumerate(resultado.fatores):
            fonte = fontes_por_codigo.get(a.codigo_fonte)
            consulta.adicionar_fator(FatorConsulta(
                ordem=ordem, codigo=a.codigo, nome=a.nome, categoria=a.categoria, situacao=a.situacao,
                pontuacao=a.pontuacao, peso=a.peso, valor_observado=_truncar(a.valor_observado, 500),
                explicacao=_truncar(a.explicacao, 2000), fonte_id=None if fonte is None else fonte.id,
                data_referencia=a.data_referencia))
        return self.consultas.salvar(consulta).id

    def buscar(self, id_consulta: uuid.UUID) -> ConsultaResponse:
        c = self.consultas.com_endereco_e_fatores(id_consulta)
        if c is None:
            raise RecursoNaoEncontrado("Consulta não encontrada.")
        e = c.endereco
        fatores = [conversores.fator(f) for f in c.fatores]
        proximas = [conversores.ocorrencia(o.ocorrencia, o.distancia_metros)
                    for o in self.coleta.ocorrencias_proximas(e.latitude, e.longitude)]
        historico = self.coleta.historico_municipal(e.estado, e.codigo_ibge)
        historico_resp = HistoricoMunicipalResponse(
            municipio_identificado=e.codigo_ibge is not None, base_importada=historico.base_importada_para_uf,
            total=len(historico.registros), registros=[conversores.ocorrencia(o) for o in historico.registros[:20]])

        codigos_fontes: dict[str, None] = {}
        if e.cep is not None:
            codigos_fontes["VIACEP"] = None
        if e.precisao != PrecisaoGeocodificacao.MANUAL:
            codigos_fontes["NOMINATIM"] = None
        if e.codigo_ibge is not None:
            codigos_fontes["IBGE_LOCALIDADES"] = None
        for f in c.fatores:
            if f.fonte is not None:
                codigos_fontes[f.fonte.codigo] = None
        if any(o.origem == "OFICIAL" for o in proximas):
            codigos_fontes["S2ID_RECONHECIMENTOS"] = None
        fontes_usadas = [conversores.fonte(f) for f in (self.fontes.buscar(cod) for cod in codigos_fontes) if f]

        return ConsultaResponse(
            id=c.id, data_consulta=c.data_consulta, endereco=conversores.endereco(e),
            classificacao=c.classificacao.value, rotulo=c.classificacao.rotulo,
            resumo=texto_classificacao(c.classificacao), indice=c.indice, justificativa=c.justificativa,
            versao_metodologia=c.versao_metodologia, dimensoes=dimensoes(c.fatores), fatores=fatores,
            ocorrencias_proximas=proximas, historico_municipal=historico_resp, mapa=_ler_mapa(c.dados_mapa),
            fontes=fontes_usadas, avisos=_avisos(e))

    def do_usuario(self, usuario_id: int) -> list[ConsultaResumo]:
        return [ConsultaResumo(id=c.id, data_consulta=c.data_consulta, endereco=c.endereco.descricao_completa(),
                               classificacao=c.classificacao.value, rotulo=c.classificacao.rotulo)
                for c in self.consultas.do_usuario(usuario_id, 50)]

    def montar_dados_mapa(self, ctx: ContextoAnalise) -> str:
        p = ctx.parametros
        raiz: dict = {"ponto": {"lat": ctx.latitude, "lon": ctx.longitude},
                      "raios": {"cursosAgua": p.raio_cursos_agua_metros, "ocorrencias": p.raio_ocorrencias_metros,
                                "setores": p.raio_setores_risco_metros}}
        limite = p.raio_cursos_agua_metros * 1.5
        cursos = raiz["cursosDagua"] = []
        if ctx.cursos_dagua.disponivel:
            com_distancia = []
            for c in ctx.cursos_dagua.valor:
                prox = proximidade_agua.mais_proximo(ctx.latitude, ctx.longitude, [c])
                com_distancia.append((c, prox.distancia_metros if prox else float("inf")))
            com_distancia.sort(key=lambda cd: cd[1])
            for c, d in com_distancia[:MAX_CURSOS_NO_MAPA]:
                linhas = []
                for parte in c.partes:
                    for trecho in recortar(parte, ctx.latitude, ctx.longitude, limite):
                        linhas.append([[casas(q[0], 6), casas(q[1], 6)] for q in trecho])
                cursos.append({"descricao": c.descricao(), "tipo": c.tipo, "principal": c.principal, "area": c.area,
                               "distanciaMetros": None if d == float("inf") else arredondar(d), "linhas": linhas})
            agua = proximidade_agua.mais_proximo(ctx.latitude, ctx.longitude, ctx.cursos_dagua.valor)
            if agua is not None:
                raiz["aguaMaisProxima"] = {"lat": casas(agua.latitude, 6), "lon": casas(agua.longitude, 6),
                                           "descricao": agua.curso.descricao(),
                                           "distanciaMetros": arredondar(agua.distancia_metros)}
        setores = raiz["setoresRisco"] = []
        if ctx.setores_risco.disponivel:
            for s in ctx.setores_risco.valor:
                setores.append({
                    "numero": s.numero_setor, "grau": s.grau_risco, "tipologia": s.tipologia, "local": s.local,
                    "hidrologico": s.hidrologico,
                    "anoSetorizacao": None if s.data_setorizacao is None else s.data_setorizacao.year,
                    "aneis": [[[casas(q[0], 6), casas(q[1], 6)] for q in anel] for anel in s.aneis]})
        return json.dumps(raiz, ensure_ascii=False, separators=(",", ":"))


def dimensoes(fatores: list[FatorConsulta]) -> list[DimensaoResponse]:
    textos = {
        CategoriaFator.RISCO_MAPEADO: ("Risco mapeado oficialmente",
                                       "Áreas de risco delimitadas por órgão oficial (Serviço Geológico do Brasil)."),
        CategoriaFator.SUSCETIBILIDADE: ("Suscetibilidade geográfica",
                                         "Características do terreno: proximidade de água e elevação relativa."),
        CategoriaFator.HISTORICO: ("Risco histórico",
                                   "Desastres oficiais registrados no município (Atlas Digital/S2iD) e ocorrências "
                                   "próximas validadas."),
    }
    lista = []
    for cat in CategoriaFator:
        da_cat = [f for f in fatores if f.categoria == cat]
        pontuacoes = [f.pontuacao for f in da_cat if f.situacao == SituacaoFator.AVALIADO and f.pontuacao is not None]
        sem_registro = any(f.situacao == SituacaoFator.SEM_REGISTRO for f in da_cat)
        if pontuacoes:
            maior = max(pontuacoes)
            nivel = {3: "FORTE", 2: "MODERADO", 1: "FRACO"}.get(maior, "SEM_INDICIO")
            rotulo = {3: "Indícios fortes", 2: "Indícios moderados", 1: "Indícios fracos"}.get(
                maior, "Sem indícios nos dados")
        elif sem_registro:
            nivel, rotulo = "SEM_REGISTRO", "Nenhum registro encontrado (não significa que nunca ocorreu)"
        else:
            nivel, rotulo = "NAO_AVALIADO", "Não avaliado (fonte indisponível)"
        titulo, descricao = textos[cat]
        lista.append(DimensaoResponse(categoria=cat.value, titulo=titulo, descricao=descricao, nivel=nivel,
                                      rotulo_nivel=rotulo))
    return lista


def _avisos(e: Endereco) -> list[str]:
    avisos = []
    if e.precisao == PrecisaoGeocodificacao.RUA:
        avisos.append("O número do imóvel não foi localizado: o ponto analisado representa a rua e pode estar a "
                      "algumas centenas de metros do imóvel. Para mais precisão, refaça a consulta confirmando a "
                      "posição no mapa.")
    avisos.append("A suscetibilidade do local resume indícios nos dados disponíveis. Não é laudo técnico nem "
                  "estudo hidrológico, e não muda com o tempo do dia.")
    avisos.append("O risco agora usa a chuva e os rios deste momento, estimados por modelos. Siga sempre os alertas "
                  "da Defesa Civil.")
    return avisos


def recortar(linha, lat: float, lon: float, limite_metros: float) -> list[list[tuple[float, float]]]:
    trechos = []
    atual: list = []
    for p in linha:
        if geo.distancia_metros(lat, lon, p[0], p[1]) <= limite_metros:
            atual.append(p)
        elif atual:
            atual.append(p)
            if len(atual) > 1:
                trechos.append(atual)
            atual = []
    if len(atual) > 1:
        trechos.append(atual)
    return trechos


def _ler_mapa(texto: str | None):
    if texto is None or not texto.strip():
        return None
    try:
        return json.loads(texto)
    except ValueError:
        return None


def _truncar(s: str | None, maximo: int) -> str | None:
    return s if s is None or len(s) <= maximo else s[: maximo - 1] + "…"
