from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from alertalar.erros import EnderecoNaoEncontrado, IntegracaoExterna, PrecisaoInsuficiente, RequisicaoInvalida
from alertalar.esquemas import Candidato as CandidatoResposta
from alertalar.esquemas import CepResponse, EnderecoRequest, LocalizacaoResponse
from alertalar.integracoes import viacep
from alertalar.integracoes.ibge import IbgeLocalidadesClient, MunicipiosIbge
from alertalar.integracoes.nominatim import ResultadoGeocodificacao
from alertalar.integracoes.viacep import DadosCep, ViaCepClient
from alertalar.modelos.entidades import Endereco
from alertalar.modelos.enums import PrecisaoGeocodificacao
from alertalar.repositorios import EnderecoRepositorio, ErroIntegridade
from alertalar.servicos.fontes import FonteDadosService
from alertalar.servicos.geocodificacao import GeocodificacaoService
from alertalar.util import geo
from alertalar.util import texto as txt

log = logging.getLogger("alertalar.enderecos")


@dataclass(frozen=True)
class Candidato:
    r: ResultadoGeocodificacao
    precisao: PrecisaoGeocodificacao | None
    fonte: str


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class EnderecoService:
    def __init__(self, via_cep: ViaCepClient, geocodificacao: GeocodificacaoService, ibge: IbgeLocalidadesClient,
                 municipios: MunicipiosIbge, repositorio: EnderecoRepositorio, fontes: FonteDadosService):
        self.via_cep = via_cep
        self.geocodificacao = geocodificacao
        self.ibge = ibge
        self.municipios = municipios
        self.repositorio = repositorio
        self.fontes = fontes

    def buscar_cep(self, cep: str) -> CepResponse:
        digitos = txt.somente_digitos(cep)
        if len(digitos) != 8:
            raise RequisicaoInvalida("O CEP deve ter 8 dígitos.")
        d = self.via_cep.buscar(digitos)
        if d is None:
            raise EnderecoNaoEncontrado(f"CEP {txt.formatar_cep(digitos)} não encontrado.")
        self.fontes.registrar_acesso("VIACEP", _agora())
        return CepResponse(cep=d.cep, rua=d.logradouro, bairro=d.bairro, cidade=d.cidade, estado=d.uf,
                           codigo_ibge=d.codigo_ibge, fonte=viacep.FONTE)

    def localizar(self, req: EnderecoRequest) -> LocalizacaoResponse:
        limpo = limpar(req)
        candidatos = self.geocodificar(limpo)
        if not candidatos:
            raise EnderecoNaoEncontrado(_mensagem_nao_encontrado(limpo))
        algum_suficiente = any(c.precisao is not None for c in candidatos)
        mensagem = ("Confira no mapa se o marcador está sobre o imóvel. Se não estiver, clique na posição correta."
                    if algum_suficiente else
                    "Encontramos apenas uma localização aproximada (bairro, cidade ou nome parecido). Clique no mapa "
                    "sobre o imóvel para confirmar a posição exata antes da análise.")
        return LocalizacaoResponse(candidatos=[CandidatoResposta(
            latitude=c.r.latitude, longitude=c.r.longitude,
            precisao="APROXIMADA" if c.precisao is None else c.precisao.value,
            descricao_precisao="Localização aproximada: precisão insuficiente" if c.precisao is None
            else c.precisao.descricao,
            suficiente_para_analise=c.precisao is not None, endereco_encontrado=c.r.nome_exibicao, fonte=c.fonte)
            for c in candidatos], mensagem=mensagem)

    def resolver_para_analise(self, req: EnderecoRequest) -> Endereco:
        limpo = limpar(req)
        dados_cep = self._consultar_cep_silencioso(limpo.cep)
        codigo_ibge = None
        if (dados_cep is not None and dados_cep.codigo_ibge is not None and dados_cep.uf.lower() == limpo.estado.lower()
                and txt.normalizar(dados_cep.cidade) == txt.normalizar(limpo.cidade)):
            codigo_ibge = dados_cep.codigo_ibge
        if codigo_ibge is None:
            codigo_ibge = self._codigo_ibge_silencioso(limpo.estado, limpo.cidade)

        if limpo.possui_coordenadas():
            if not geo.dentro_do_brasil(limpo.latitude, limpo.longitude):
                raise RequisicaoInvalida("As coordenadas informadas estão fora do território brasileiro.")
            e = _novo_endereco(limpo, codigo_ibge, dados_cep)
            e.latitude = limpo.latitude
            e.longitude = limpo.longitude
            e.precisao = PrecisaoGeocodificacao.MANUAL
            e.fonte_geocodificacao = "Posição confirmada pelo usuário no mapa"
            return self.repositorio.salvar(e)

        chave_end = chave(limpo)
        em_cache = self.repositorio.por_chave(chave_end)
        if em_cache is not None:
            if txt.vazio(em_cache.codigo_ibge) and not txt.vazio(codigo_ibge):
                em_cache.codigo_ibge = codigo_ibge
                return self.repositorio.salvar(em_cache)
            return em_cache
        candidatos = self.geocodificar(limpo)
        if not candidatos:
            raise EnderecoNaoEncontrado(_mensagem_nao_encontrado(limpo))
        melhor = candidatos[0]
        if melhor.precisao is None:
            raise PrecisaoInsuficiente("O endereço foi localizado apenas de forma aproximada (bairro, CEP ou cidade). "
                                       "Para não analisar o imóvel errado, confirme a posição exata clicando no mapa.",
                                       melhor.r.latitude, melhor.r.longitude)
        e = _novo_endereco(limpo, codigo_ibge, dados_cep)
        e.latitude = melhor.r.latitude
        e.longitude = melhor.r.longitude
        e.precisao = melhor.precisao
        e.fonte_geocodificacao = melhor.fonte
        e.chave_normalizada = chave_end
        try:
            return self.repositorio.salvar(e)
        except ErroIntegridade:
            concorrente = self.repositorio.por_chave(chave_end)
            if concorrente is None:
                raise
            return concorrente

    def geocodificar(self, req: EnderecoRequest) -> list[Candidato]:
        busca = self.geocodificacao.buscar(req, lambda resultados: _filtrar(resultados, req))
        candidatos = [Candidato(r, precisao(r, req.numero), busca.fonte) for r in busca.resultados]
        return sorted(candidatos, key=lambda c: (9 if c.precisao is None else c.precisao.ordem, -c.r.place_rank))

    def _consultar_cep_silencioso(self, cep: str | None) -> DadosCep | None:
        if len(txt.somente_digitos(cep)) != 8:
            return None
        try:
            return self.via_cep.buscar(cep)
        except IntegracaoExterna:
            log.info("ViaCEP indisponível; seguindo sem dados do CEP")
            return None

    def _codigo_ibge_silencioso(self, uf: str, cidade: str) -> str | None:
        local = self.municipios.codigo(uf, cidade)
        if local is not None:
            return local
        try:
            codigo = self.ibge.codigo_municipio(uf, cidade)
            if codigo is not None:
                self.fontes.registrar_acesso("IBGE_LOCALIDADES", _agora())
            return codigo
        except IntegracaoExterna:
            log.info("API do IBGE indisponível; código do município não identificado")
            return None


def _filtrar(resultados: list[ResultadoGeocodificacao], req: EnderecoRequest) -> list[ResultadoGeocodificacao]:
    cidade = txt.normalizar(req.cidade)
    return [r for r in resultados
            if (r.uf is None or r.uf.lower() == (req.estado or "").lower())
            and (r.cidade is None or txt.normalizar(r.cidade) == cidade or cidade in txt.normalizar(r.nome_exibicao))]


def precisao(r: ResultadoGeocodificacao, numero_pedido: str | None) -> PrecisaoGeocodificacao | None:
    pedido = txt.normalizar(numero_pedido)
    mesmo_numero = r.numero is not None and pedido != "" and txt.normalizar(r.numero) == pedido
    if mesmo_numero and r.place_rank >= 26:
        return PrecisaoGeocodificacao.NUMERO
    if r.place_rank >= 26 and r.rua is not None:
        return PrecisaoGeocodificacao.RUA
    return None


def _novo_endereco(req: EnderecoRequest, codigo_ibge: str | None, dados_cep: DadosCep | None) -> Endereco:
    return Endereco(cep=txt.formatar_cep(req.cep), rua=req.rua, numero=req.numero,
                    bairro=req.bairro if req.bairro is not None else (dados_cep.bairro if dados_cep else None),
                    cidade=req.cidade, estado=req.estado, codigo_ibge=codigo_ibge)


def limpar(r: EnderecoRequest) -> EnderecoRequest:
    return EnderecoRequest(
        cep=None if txt.vazio(r.cep) else txt.formatar_cep(r.cep), rua=txt.limpar(r.rua), numero=txt.limpar(r.numero),
        bairro=txt.limpar(r.bairro), cidade=txt.limpar(r.cidade),
        estado=None if r.estado is None else r.estado.strip().upper(), latitude=r.latitude, longitude=r.longitude)


def chave(r: EnderecoRequest) -> str:
    return "|".join((txt.normalizar(r.rua), txt.normalizar(r.numero), txt.normalizar(r.cidade), r.estado.upper()))


def _mensagem_nao_encontrado(r: EnderecoRequest) -> str:
    return (f"Não encontramos o endereço \"{r.rua}{'' if txt.vazio(r.numero) else ', ' + r.numero}\" em "
            f"{r.cidade}/{r.estado}. Confira o nome da rua e da cidade, ou marque a posição do imóvel diretamente "
            "no mapa.")
