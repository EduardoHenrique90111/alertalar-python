from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from alertalar.erros import IntegracaoExterna
from alertalar.esquemas import EnderecoRequest
from alertalar.integracoes import nominatim as nominatim_mod
from alertalar.integracoes import photon as photon_mod
from alertalar.integracoes.http import CacheTemporario
from alertalar.integracoes.nominatim import NominatimClient, ResultadoGeocodificacao
from alertalar.integracoes.photon import PhotonClient
from alertalar.servicos.fontes import FonteDadosService
from alertalar.util import texto as txt
from alertalar.util.uf import UnidadeFederativa

log = logging.getLogger("alertalar.geocodificacao")

PAUSA_LIMITE = timedelta(minutes=5)
PAUSA_BLOQUEIO = timedelta(minutes=30)
PAUSA_FALHA = timedelta(minutes=1)
PAUSA_MAXIMA = timedelta(minutes=30)
LIMITE_RESULTADOS = 5
LIMITE_RESULTADOS_PHOTON = 10

MENSAGEM_INDISPONIVEL = ("A busca de endereços do OpenStreetMap está sobrecarregada agora. "
                         "Tente de novo em alguns segundos ou marque a posição direto no mapa.")

PALAVRAS_GENERICAS = frozenset({"rua", "avenida", "travessa", "estrada", "rodovia", "alameda", "praca", "largo",
                                "beco", "via", "das", "dos", "del", "para"})

Filtro = Callable[[list[ResultadoGeocodificacao]], list[ResultadoGeocodificacao]]


@dataclass(frozen=True)
class Busca:
    resultados: list[ResultadoGeocodificacao]
    fonte: str


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class GeocodificacaoService:
    def __init__(self, nominatim: NominatimClient, photon: PhotonClient, fontes: FonteDadosService,
                 relogio: Callable[[], datetime] = _agora):
        self.nominatim = nominatim
        self.photon = photon
        self.fontes = fontes
        self._relogio = relogio
        self._cache: CacheTemporario[str, Busca] = CacheTemporario(24 * 3600, 2_000,
                                                                   relogio=lambda: self._relogio().timestamp())
        self._nominatim_pausado_ate = datetime.min.replace(tzinfo=timezone.utc)

    def buscar(self, req: EnderecoRequest, filtro: Filtro) -> Busca:
        chave = _chave(req)
        guardada = self._cache.obter(chave)
        if guardada is not None:
            return guardada
        pausado = self.nominatim_em_pausa()
        ordem = ("PHOTON", "NOMINATIM") if pausado else ("NOMINATIM", "PHOTON")
        falhas: list[IntegracaoExterna] = []
        respondeu = None
        for servico in ordem:
            if servico == "NOMINATIM" and pausado and respondeu is not None:
                break
            fonte = nominatim_mod.FONTE if servico == "NOMINATIM" else photon_mod.FONTE
            try:
                resultados = (self._tentativas_nominatim(req, filtro) if servico == "NOMINATIM"
                              else self._tentativas_photon(req, filtro))
                respondeu = respondeu or fonte
                if servico == "NOMINATIM":
                    self._nominatim_pausado_ate = datetime.min.replace(tzinfo=timezone.utc)
                    self.fontes.registrar_acesso("NOMINATIM", self._relogio())
                else:
                    self.fontes.registrar_acesso("PHOTON", self._relogio())
                if resultados:
                    busca = Busca(resultados, fonte)
                    self._cache.guardar(chave, busca)
                    return busca
            except IntegracaoExterna as e:
                falhas.append(e)
                if servico == "NOMINATIM":
                    self._pausar_nominatim(e)
                else:
                    log.warning("Photon também falhou: %s", e)
        if respondeu is not None:
            return Busca([], respondeu)
        raise IntegracaoExterna("OpenStreetMap", MENSAGEM_INDISPONIVEL) from (falhas[0] if falhas else None)

    def _tentativas_nominatim(self, req: EnderecoRequest, filtro: Filtro) -> list[ResultadoGeocodificacao]:
        r = filtro(self.nominatim.buscar_estruturado(req.rua, req.numero, req.cidade, req.estado, LIMITE_RESULTADOS))
        if not r:
            texto = (req.rua + ("" if txt.vazio(req.numero) else ", " + req.numero)
                     + ("" if txt.vazio(req.bairro) else ", " + req.bairro)
                     + f", {req.cidade} - {req.estado}, Brasil")
            r = filtro(self.nominatim.buscar_texto(texto, LIMITE_RESULTADOS))
        junto = nome_junto(req)
        if not r and junto is not None:
            r = filtro(self.nominatim.buscar_texto(f"{junto}, {req.cidade} - {req.estado}, Brasil", LIMITE_RESULTADOS))
        return r

    def _tentativas_photon(self, req: EnderecoRequest, filtro: Filtro) -> list[ResultadoGeocodificacao]:
        estado = UnidadeFederativa.da_sigla(req.estado)
        lugar = f", {req.cidade}, {estado.nome if estado else req.estado}"
        r = filtro(self.photon.buscar(req.rua + ("" if txt.vazio(req.numero) else " " + req.numero) + lugar,
                                      LIMITE_RESULTADOS_PHOTON))
        junto = nome_junto(req)
        if not r and junto is not None:
            r = filtro(self.photon.buscar(junto + lugar, LIMITE_RESULTADOS_PHOTON))
        return [conferir_nome(item, req.rua) for item in r][:LIMITE_RESULTADOS]

    def nominatim_em_pausa(self) -> bool:
        return self._relogio() < self._nominatim_pausado_ate

    def _pausar_nominatim(self, e: IntegracaoExterna) -> None:
        duracao = pausa(e)
        self._nominatim_pausado_ate = self._relogio() + duracao
        log.warning("Nominatim indisponível (%s); buscas de endereço vão primeiro ao Photon por %d min",
                    e, max(1, int(duracao.total_seconds() // 60)))


def conferir_nome(r: ResultadoGeocodificacao, rua_pedida: str) -> ResultadoGeocodificacao:
    if nome_confere(rua_pedida, r.nome_exibicao) or r.place_rank < 26:
        return r
    return r.com_rank(20)


def nome_confere(pedido: str | None, encontrado: str | None) -> bool:
    alvo = re.sub(r"[^a-z0-9 ]", " ", txt.normalizar(encontrado))
    for palavra in re.split(r" +", re.sub(r"[^a-z0-9 ]", " ", txt.normalizar(pedido))):
        if len(palavra) < 3 or palavra in PALAVRAS_GENERICAS or re.fullmatch(r"\d+", palavra):
            continue
        if palavra not in alvo:
            return False
    return True


def nome_junto(req: EnderecoRequest) -> str | None:
    if not txt.vazio(req.numero) or txt.vazio(req.rua):
        return None
    palavras = req.rua.strip().split()
    if len(palavras) < 2 or len(palavras) > 3 or re.match(
            r"^(rua|r\.|avenida|av\.?|travessa|estrada|rodovia)\b", req.rua, re.IGNORECASE):
        return None
    return "".join(palavras)


def pausa(e: IntegracaoExterna) -> timedelta:
    status = e.status_http or 0
    if status == 429:
        if e.espera_pedida is None:
            return PAUSA_LIMITE
        pedida = timedelta(seconds=e.espera_pedida)
        return PAUSA_FALHA if pedida < PAUSA_FALHA else PAUSA_MAXIMA if pedida > PAUSA_MAXIMA else pedida
    if status == 403:
        return PAUSA_BLOQUEIO
    return PAUSA_FALHA


def _chave(req: EnderecoRequest) -> str:
    return "|".join((txt.normalizar(req.rua), txt.normalizar(req.numero), txt.normalizar(req.bairro),
                     txt.normalizar(req.cidade), "" if req.estado is None else req.estado.upper()))
