"""Registro, listagem e moderação de ocorrências. Relatos de usuários entram como PENDENTE e só
passam a contar na análise de risco quando um administrador os CONFIRMA."""

from __future__ import annotations

from datetime import datetime, timezone

from alertalar.erros import IntegracaoExterna, RecursoNaoEncontrado, RegraNegocio
from alertalar.esquemas import OcorrenciaAdminResponse, OcorrenciaRequest, OcorrenciaResponse, PaginaResponse, ValidacaoRequest
from alertalar.integracoes.ibge import IbgeLocalidadesClient
from alertalar.modelos.entidades import Ocorrencia, Usuario
from alertalar.modelos.enums import NivelLocalizacao, OrigemOcorrencia, StatusValidacao
from alertalar.repositorios import OcorrenciaRepositorio, Pagina
from alertalar.servicos import conversores
from alertalar.servicos.coleta import ColetaDadosService
from alertalar.servicos.fontes import FonteDadosService
from alertalar.util import geo
from alertalar.util import texto as txt

FONTE_RELATOS = "ALERTALAR_RELATOS"
TAMANHO_MAXIMO_PAGINA = 100


def _limitar(valor: int, minimo: int, maximo: int) -> int:
    return max(minimo, min(maximo, valor))


def _pagina(p: Pagina, conversor) -> PaginaResponse:
    return PaginaResponse(itens=[conversor(o) for o in p.itens], pagina=p.pagina, tamanho=p.tamanho, total=p.total,
                          total_paginas=p.total_paginas)


class OcorrenciaService:
    def __init__(self, repositorio: OcorrenciaRepositorio, fontes: FonteDadosService, ibge: IbgeLocalidadesClient,
                 coleta: ColetaDadosService):
        self.repositorio = repositorio
        self.fontes = fontes
        self.ibge = ibge
        self.coleta = coleta

    def registrar_relato(self, req: OcorrenciaRequest, usuario: Usuario | None) -> OcorrenciaResponse:
        if req.latitude is not None and not geo.dentro_do_brasil(req.latitude, req.longitude):
            raise RegraNegocio("As coordenadas informadas estão fora do território brasileiro.")
        uf = req.estado.strip().upper()
        municipio = txt.limpar(req.municipio)
        o = Ocorrencia(
            localizacao=txt.limpar(req.localizacao), municipio=municipio, estado=uf,
            codigo_ibge=self._codigo_ibge(uf, municipio), data_ocorrencia=req.data_ocorrencia,
            descricao=txt.limpar(req.descricao), tipo_evento=req.tipo_evento, origem=OrigemOcorrencia.RELATO_USUARIO,
            status_validacao=StatusValidacao.PENDENTE, latitude=req.latitude, longitude=req.longitude,
            nivel_localizacao=NivelLocalizacao.PONTO if req.latitude is not None else NivelLocalizacao.MUNICIPIO,
            fonte_id=self.fontes.obrigatoria(FONTE_RELATOS).id, nome_relator=txt.limpar(req.nome_relator),
            contato_relator=txt.limpar(req.contato_relator), usuario_id=None if usuario is None else usuario.id,
            data_registro=datetime.now(timezone.utc))
        if o.nome_relator is None and usuario is not None:
            o.nome_relator = usuario.nome
        return conversores.ocorrencia(self.repositorio.salvar(o))

    def listar_confirmadas(self, estado: str | None, municipio: str | None, origem: OrigemOcorrencia | None,
                           pagina: int, tamanho: int) -> PaginaResponse[OcorrenciaResponse]:
        """Listagem pública (somente ocorrências confirmadas)."""
        uf = None if txt.vazio(estado) else estado.strip().upper()
        mun = None if txt.vazio(municipio) else municipio.strip().lower()
        p = self.repositorio.listar_confirmadas(uf, mun, origem, max(0, pagina),
                                                _limitar(tamanho, 1, TAMANHO_MAXIMO_PAGINA))
        return _pagina(p, conversores.ocorrencia)

    def confirmadas_proximas(self, lat: float, lon: float, raio_metros: int, anos: int) -> list[OcorrenciaResponse]:
        """Ocorrências confirmadas com coordenadas ao redor de um ponto (para o mapa)."""
        if not geo.dentro_do_brasil(lat, lon):
            raise RegraNegocio("As coordenadas informadas estão fora do território brasileiro.")
        raio = _limitar(raio_metros, 50, 10_000)
        return [conversores.ocorrencia(p.ocorrencia, p.distancia_metros)
                for p in self.coleta.ocorrencias_no_raio(lat, lon, raio, _limitar(anos, 1, 100))]

    def listar_para_moderacao(self, status: StatusValidacao, busca: str | None, pagina: int,
                              tamanho: int) -> PaginaResponse[OcorrenciaAdminResponse]:
        """Relatos de usuários para a moderação, do mais recente para o mais antigo, com busca opcional
        (local, município, descrição, nome ou contato do relator). Registros oficiais ficam de fora."""
        p = self.repositorio.listar_relatos_para_moderacao(status, padrao_busca(busca), max(0, pagina),
                                                           _limitar(tamanho, 1, TAMANHO_MAXIMO_PAGINA))
        return _pagina(p, conversores.ocorrencia_admin)

    def validar(self, id_ocorrencia: int, req: ValidacaoRequest, moderador: Usuario) -> OcorrenciaAdminResponse:
        if req.status == StatusValidacao.PENDENTE:
            raise RegraNegocio("A decisão deve ser CONFIRMADA ou REJEITADA.")
        o = self.repositorio.por_id(id_ocorrencia)
        if o is None:
            raise RecursoNaoEncontrado("Ocorrência não encontrada.")
        if o.origem == OrigemOcorrencia.OFICIAL:
            raise RegraNegocio("Registros oficiais não passam por moderação.")
        agora = datetime.now(timezone.utc)
        o.status_validacao = req.status
        o.observacao_validacao = txt.limpar(req.observacao)
        o.validado_por_id = moderador.id
        o.data_validacao = agora
        gravada = self.repositorio.salvar(o)
        if req.status == StatusValidacao.CONFIRMADA:
            self.fontes.registrar_acesso(FONTE_RELATOS, agora)
        return conversores.ocorrencia_admin(gravada)

    def contar_pendentes(self) -> int:
        return self.repositorio.contar_por_status(StatusValidacao.PENDENTE)

    def _codigo_ibge(self, uf: str, municipio: str | None) -> str | None:
        try:
            return self.ibge.codigo_municipio(uf, municipio)
        except IntegracaoExterna:
            return None


def padrao_busca(busca: str | None) -> str | None:
    """"Dom João" → "%dom joão%", com %, _ e ! escapados (o texto digitado nunca vira curinga)."""
    limpo = txt.limpar(busca)
    if limpo is None:
        return None
    escapado = limpo.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escapado}%"
