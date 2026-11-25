"""Rota segura até um destino escolhido pela pessoa (endereço, nome do local ou ponto no mapa):
calcula o caminho pelas ruas, a pé ou de carro, pedindo ao roteador que evite os setores de risco
hidrológico do SGB entre a partida e o destino.

Depois confere o caminho: setores que ele ainda atravessa e o perfil de altura (trechos mais baixos
que a partida geram aviso). Também avisa se o destino fica dentro de uma área de risco ou mais
baixo que a partida. É uma sugestão baseada em dados públicos, não uma rota oficial de evacuação.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from alertalar.erros import IntegracaoExterna, RegraNegocio
from alertalar.esquemas import Destino, InstrucaoRota, Perfil, Ponto, RotaSeguraResponse, SetorMapa, Trajeto
from alertalar.integracoes.http import CacheTemporario
from alertalar.integracoes.open_meteo import ElevacaoClient
from alertalar.integracoes.sgb import SetorRisco, SgbSetoresRiscoClient
from alertalar.integracoes.valhalla import ModoRota, Rota, ValhallaClient
from alertalar.servicos.analise.dado import Dado
from alertalar.servicos.fontes import FonteDadosService
from alertalar.servicos.progresso_rota import NENHUM, CalculoCancelado, Estado, Etapa, Evento, ProgressoRota
from alertalar.util import geo, numeros
from alertalar.util.numeros import arredondar

log = logging.getLogger("alertalar.rota")

# O Valhalla limita o perímetro total dos polígonos evitados (padrão de 10 km)
PERIMETRO_MAXIMO_EVITAR = 9000
AMOSTRAS_PERFIL = 60
TOLERANCIA_TRECHO_BAIXO = 2
# Distância máxima em linha reta até o destino (o desvio de áreas de risco tem limite de perímetro)
DISTANCIA_MAXIMA_DESTINO = 20_000
DISTANCIA_MINIMA_DESTINO = 30
SEM_PERFIL = ("Não foi possível consultar a altura do terreno ao longo do caminho agora, então ele não foi "
              "conferido quanto a trechos mais baixos. Fique atento a ruas em baixada.")


@dataclass(frozen=True)
class Evitar:
    aneis: list
    omitidos: int


class RotaSeguraService:
    def __init__(self, elevacao: ElevacaoClient, sgb: SgbSetoresRiscoClient, roteador: ValhallaClient,
                 fontes: FonteDadosService):
        self.elevacao = elevacao
        self.sgb = sgb
        self.roteador = roteador
        self.fontes = fontes
        self._cache: CacheTemporario[str, RotaSeguraResponse] = CacheTemporario(15 * 60, 1_000)
        self._executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="rota")

    def encerrar(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def calcular(self, lat: float, lon: float, lat_destino: float, lon_destino: float, modo: ModoRota,
                 progresso: ProgressoRota = NENHUM) -> RotaSeguraResponse:
        """Rota até o destino escolhido, avisando o andamento de cada consulta externa."""
        self.validar(lat, lon, lat_destino, lon_destino)
        chave = f"{lat:.4f},{lon:.4f}>{lat_destino:.4f},{lon_destino:.4f},{modo.value}"
        return self._cache.obter_ou_calcular(
            chave, lambda: self._calcular_sem_cache(lat, lon, lat_destino, lon_destino, modo, progresso))

    def validar(self, lat: float, lon: float, lat_destino: float, lon_destino: float) -> None:
        """Confere partida e destino antes de começar (o erro volta como resposta comum, não no meio
        do andamento)."""
        if not geo.dentro_do_brasil(lat, lon) or not geo.dentro_do_brasil(lat_destino, lon_destino):
            raise RegraNegocio("A partida e o destino precisam estar no território brasileiro.")
        distancia = geo.distancia_metros(lat, lon, lat_destino, lon_destino)
        if distancia < DISTANCIA_MINIMA_DESTINO:
            raise RegraNegocio("O destino está no mesmo lugar da partida. Escolha outro destino.")
        if distancia > DISTANCIA_MAXIMA_DESTINO:
            raise RegraNegocio(f"O destino está a {formatar_distancia(distancia)} em linha reta. A rota segura calcula "
                               "caminhos de até 20 km; escolha um destino mais perto.")

    def _calcular_sem_cache(self, lat: float, lon: float, lat_d: float, lon_d: float, modo: ModoRota,
                            progresso: ProgressoRota) -> RotaSeguraResponse:
        distancia = geo.distancia_metros(lat, lon, lat_d, lon_d)
        raio = int(min(12_000, distancia / 2 + 1_500))
        lat_meio = (lat + lat_d) / 2
        lon_meio = (lon + lon_d) / 2
        pontos = [(lat, lon), (lat_d, lon_d)]
        a = Andamento(progresso)
        a.plano()
        a.iniciar(Etapa.ALTURA, "partida e destino")
        a.iniciar(Etapa.SETORES, f"num raio de {formatar_distancia(raio)} em volta do trajeto")
        futuro_elevacao = self._executor.submit(
            lambda: a.terminar_altura(Dado.coletar(lambda: self.elevacao.elevacoes(pontos))))
        futuro_setores = self._executor.submit(
            lambda: a.terminar_setores(Dado.coletar(lambda: self.sgb.buscar_proximos(lat_meio, lon_meio, raio))))
        elevacoes = futuro_elevacao.result()
        setores = futuro_setores.result()

        m = Montador(modo, a)
        hidrologicos = self._setores_hidrologicos(m, setores)
        e0 = e_d = None
        if elevacoes.disponivel and len(elevacoes.valor) >= 2:
            self.fontes.registrar_acesso("COPERNICUS_DEM", elevacoes.obtido_em)
            m.fontes.append("Altura do terreno: Copernicus DEM GLO-90 (via Open-Meteo)")
            e0, e_d = elevacoes.valor[0], elevacoes.valor[1]
        origem = Ponto(latitude=lat, longitude=lon, elevacao=None if e0 is None else _arred(e0))

        setor_da_origem = setor_que_contem(hidrologicos, lat, lon)
        if setor_da_origem is not None:
            m.avisos.append(f"O ponto de partida está dentro de uma área de risco de {_tipologia(setor_da_origem)} "
                            f"mapeada pelo SGB{_descricao_setor(setor_da_origem)}. Saia dela o quanto antes.")
        setor_do_destino = setor_que_contem(hidrologicos, lat_d, lon_d)
        if setor_do_destino is not None:
            m.avisos.append(f"O destino escolhido fica dentro de uma área de risco de {_tipologia(setor_do_destino)} "
                            f"mapeada pelo SGB{_descricao_setor(setor_do_destino)}. Em caso de enchente, prefira um "
                            "lugar mais alto e fora das áreas de risco.")
        ganho = None if e0 is None or e_d is None else e_d - e0
        if ganho is not None and ganho < -TOLERANCIA_TRECHO_BAIXO:
            m.avisos.append(f"O destino fica cerca de {arredondar(-ganho)} m mais baixo que o ponto de partida. "
                            "Em caso de enchente, prefira um lugar mais alto.")
        if ganho is None:
            complemento = "."
        elif abs(ganho) < 1:
            complemento = ", na mesma altura da partida."
        else:
            complemento = (f", cerca de {arredondar(abs(ganho))} m mais {'alto' if ganho > 0 else 'baixo'} "
                           "que a partida.")
        destino = Destino(latitude=lat_d, longitude=lon_d, elevacao=None if e_d is None else _arred(e_d),
                          ganho_elevacao=None if ganho is None else _arred(ganho),
                          distancia_reta_metros=float(arredondar(distancia)),
                          descricao=f"Destino escolhido, a {formatar_distancia(distancia)} em linha reta{complemento}")

        evitar = poligonos_a_evitar(hidrologicos, lat, lon, lat_d, lon_d)
        rota = None
        desvio_aplicado = True
        if evitar.aneis:
            a.iniciar(Etapa.CAMINHO, detalhe_desvio(evitar))
            rota = self._tentar_rota(a, lat, lon, lat_d, lon_d, modo, evitar.aneis)
        if rota is None:
            a.iniciar(Etapa.CAMINHO, detalhe_desvio(evitar) if not evitar.aneis
                      else "nova tentativa, sem o desvio (a anterior não deu certo)")
            rota = self._tentar_rota(a, lat, lon, lat_d, lon_d, modo, [])
            desvio_aplicado = not evitar.aneis
        if rota is None:
            a.falhar(Etapa.CAMINHO, "o serviço de rotas não conseguiu traçar o caminho agora")
            m.destino = destino
            return m.sem_rota("ROTA_INDISPONIVEL", origem, "O serviço de rotas não conseguiu traçar o caminho até o "
                                                           "destino agora. Tente novamente em instantes.")
        self._registrar_roteador(m, desvio_aplicado, evitar)
        conhecidos = [s for s in (setor_da_origem, setor_do_destino) if s is not None]
        return self._montar_com_rota(m, origem, e0, destino, rota, desvio_aplicado,
                                     len(evitar.aneis) if desvio_aplicado else 0, hidrologicos, conhecidos)

    def _setores_hidrologicos(self, m: Montador, setores: Dado[list[SetorRisco]]) -> list[SetorRisco]:
        hidrologicos: list[SetorRisco] = []
        if setores.disponivel:
            self.fontes.registrar_acesso("SGB_SETORES_RISCO", setores.obtido_em)
            m.fontes.append("Áreas de risco: Serviço Geológico do Brasil (setorização de riscos)")
            hidrologicos = [s for s in setores.valor if s.hidrologico]
            m.setores.extend(SetorMapa(numero=s.numero_setor, grau=s.grau_risco, tipologia=s.tipologia,
                                       aneis=[list(anel) for anel in s.aneis]) for s in hidrologicos)
        else:
            m.avisos.append("Não foi possível consultar as áreas de risco do Serviço Geológico do Brasil agora; "
                            "o caminho abaixo não desvia delas.")
        return hidrologicos

    def _registrar_roteador(self, m: Montador, desvio_aplicado: bool, evitar: Evitar) -> None:
        self.fontes.registrar_acesso("VALHALLA_ROTAS", datetime.now(timezone.utc))
        m.fontes.append("Caminho: Valhalla (FOSSGIS) com dados de vias © colaboradores do OpenStreetMap")
        if not desvio_aplicado:
            m.avisos.append("Não foi possível calcular um caminho que desvie das áreas de risco mapeadas; "
                            "o trajeto abaixo pode passar por elas.")
        elif evitar.omitidos > 0:
            m.avisos.append(f"Há muitas áreas de risco na região; o desvio considerou as {len(evitar.aneis)} mais "
                            "próximas do caminho.")

    def _tentar_rota(self, a: Andamento, lat: float, lon: float, lat_d: float, lon_d: float, modo: ModoRota,
                     evitar: list) -> Rota | None:
        a.verificar_cancelamento()
        try:
            return self.roteador.rota(lat, lon, lat_d, lon_d, modo, evitar)
        except IntegracaoExterna as e:
            log.info("Rota até %s,%s falhou (%d polígonos evitados): %s", lat_d, lon_d, len(evitar), e)
            return None

    def _montar_com_rota(self, m: Montador, origem: Ponto, e0: float | None, destino: Destino, rota: Rota,
                         desvio_aplicado: bool, setores_evitados: int, hidrologicos: list[SetorRisco],
                         setores_conhecidos: list[SetorRisco]) -> RotaSeguraResponse:
        """``setores_conhecidos``: setores da partida/destino, já avisados (não contam como atravessados)."""
        m.andamento.concluir(Etapa.CAMINHO, formatar_distancia(rota.distancia_metros) + " pelas ruas")
        m.destino = destino
        instrucoes = [InstrucaoRota(texto=i.texto, distancia_metros=float(arredondar(i.distancia_metros)),
                                    duracao_segundos=float(arredondar(i.duracao_segundos)))
                      for i in rota.instrucoes if i.texto is not None]
        m.trajeto = Trajeto(distancia_metros=float(arredondar(rota.distancia_metros)),
                            duracao_segundos=float(arredondar(rota.duracao_segundos)), coordenadas=rota.pontos,
                            instrucoes=instrucoes, desvio_areas_risco_aplicado=desvio_aplicado,
                            setores_evitados=setores_evitados)

        # Setores de risco atravessados pelo caminho (exceto os da partida e do destino)
        atravessados: dict[str, None] = {}
        for p in geo.amostrar(rota.pontos, min(200, max(20, len(rota.pontos)))):
            s = setor_que_contem(hidrologicos, p[0], p[1])
            if s is not None and not any(s is c for c in setores_conhecidos):
                atravessados["sem número" if s.numero_setor is None else s.numero_setor] = None
        if atravessados:
            m.avisos.append(f"O caminho passa por dentro de área de risco mapeada pelo SGB (setor "
                            f"{', '.join(atravessados)}). Atenção redobrada nesse trecho e não atravesse se houver água.")

        # Perfil de elevação do caminho
        amostras = geo.amostrar(rota.pontos, AMOSTRAS_PERFIL)
        m.andamento.verificar_cancelamento()
        m.andamento.iniciar(Etapa.PERFIL, f"{len(amostras)} pontos do caminho")
        elev_perfil = Dado.coletar(lambda: self.elevacao.elevacoes([(q[0], q[1]) for q in amostras]))
        if not elev_perfil.disponivel:
            m.andamento.falhar(Etapa.PERFIL, "não foi possível conferir agora; o caminho continua valendo")
            m.avisos.append(SEM_PERFIL)
        else:
            perfil = []
            minimo, maximo = float("inf"), float("-inf")
            ponto_min = None
            dist_min = 0.0
            for amostra, e in zip(amostras, elev_perfil.valor):
                if e is None:
                    continue
                perfil.append((float(arredondar(amostra[2])), _arred(e)))
                if e < minimo:
                    minimo = e
                    ponto_min = (amostra[0], amostra[1])
                    dist_min = amostra[2]
                maximo = max(maximo, e)
            if ponto_min is None:
                m.andamento.falhar(Etapa.PERFIL, "o serviço não trouxe a altura dos pontos; o caminho continua valendo")
                m.avisos.append(SEM_PERFIL)
            else:
                m.andamento.concluir(Etapa.PERFIL, f"trecho mais baixo a {arredondar(minimo)} m de altitude")
                m.perfil = Perfil(elevacao_minima=_arred(minimo), elevacao_maxima=_arred(maximo),
                                  distancia_ponto_mais_baixo=float(arredondar(dist_min)), ponto_mais_baixo=ponto_min,
                                  amostras=perfil)
                if e0 is not None and minimo < e0 - TOLERANCIA_TRECHO_BAIXO and dist_min > 50:
                    m.avisos.append(f"Atenção: a cerca de {arredondar(dist_min)} m do início, o caminho passa por um "
                                    f"trecho {arredondar(e0 - minimo)} m mais baixo que o ponto de partida (marcado no "
                                    "mapa). Se esse trecho estiver alagado, não atravesse: procure outro caminho ou um "
                                    "andar alto de um prédio próximo.")

        tempo = formatar_tempo(rota.duracao_segundos)
        mensagem = (f"Siga por {formatar_distancia(rota.distancia_metros)} (cerca de {tempo} "
                    f"{'a pé' if m.modo == ModoRota.A_PE else 'de carro'}) até o destino escolhido.")
        return m.com_rota(origem, mensagem)


# ------------------------------------------------------------------ áreas a evitar

def poligonos_a_evitar(hidrologicos: list[SetorRisco], lat: float, lon: float, lat_d: float, lon_d: float) -> Evitar:
    """Setores a evitar: todos os hidrológicos que não contêm a origem nem o destino, dos mais
    próximos do trajeto em linha reta para os mais distantes, até o limite de perímetro aceito pelo
    roteador."""
    segmento = [(lat, lon), (lat_d, lon_d)]
    aneis = []
    for s in hidrologicos:
        if any(geo.dentro_do_poligono(lat, lon, anel) or geo.dentro_do_poligono(lat_d, lon_d, anel) for anel in s.aneis):
            continue
        for anel in s.aneis:
            centro = _centroide(anel)
            mais_perto = geo.ponto_mais_proximo(centro[0], centro[1], segmento)
            fechado = list(anel)
            if tuple(fechado[0]) != tuple(fechado[-1]):
                fechado.append(fechado[0])
            aneis.append((anel, float("inf") if mais_perto is None else mais_perto[2], geo.comprimento(fechado)))
    aneis.sort(key=lambda item: item[1])
    escolhidos = []
    total = 0.0
    omitidos = 0
    for anel, _distancia, perimetro in aneis:
        if total + perimetro <= PERIMETRO_MAXIMO_EVITAR:
            escolhidos.append(anel)
            total += perimetro
        else:
            omitidos += 1
    return Evitar(escolhidos, omitidos)


def setor_que_contem(setores: list[SetorRisco], lat: float, lon: float) -> SetorRisco | None:
    for s in setores:
        for anel in s.aneis:
            if geo.dentro_do_poligono(lat, lon, anel):
                return s
    return None


def _centroide(anel) -> tuple[float, float]:
    return sum(p[0] for p in anel) / len(anel), sum(p[1] for p in anel) / len(anel)


def _tipologia(s: SetorRisco) -> str:
    return "inundação" if s.tipologia is None else s.tipologia.lower()


def _descricao_setor(s: SetorRisco) -> str:
    partes = []
    if s.numero_setor is not None:
        partes.append("setor " + s.numero_setor)
    if s.grau_risco is not None:
        partes.append("grau " + s.grau_risco.lower())
    return "" if not partes else f" ({', '.join(partes)})"


def formatar_distancia(metros: float) -> str:
    if metros < 1000:
        return f"{arredondar(metros / 10.0) * 10} m"
    return (numeros.decimal(metros / 1000, 1, virgula=True) + " km").replace(",0 km", " km")


def formatar_tempo(segundos: float) -> str:
    minutos = max(1, arredondar(segundos / 60))
    return f"{minutos} min" if minutos < 60 else f"{minutos // 60} h {minutos % 60} min"


def detalhe_desvio(evitar: Evitar) -> str:
    n = len(evitar.aneis)
    if n == 0:
        return "traçando o caminho"
    return f"desviando de {n}" + (" área" if n == 1 else " áreas") + " de risco"


def _arred(v: float) -> float:
    return numeros.casas(v, 1)


class Andamento:
    """Envia o andamento das etapas para quem acompanha o cálculo (a tela, via :class:`ProgressoRota`)."""

    def __init__(self, progresso: ProgressoRota):
        self.progresso = progresso

    def plano(self) -> None:
        """Todas as etapas como pendentes, para a tela já mostrar o que vem pela frente."""
        for e in Etapa:
            self._informar(e, Estado.PENDENTE, None)

    def iniciar(self, etapa: Etapa, detalhe: str | None) -> None:
        self._informar(etapa, Estado.EM_ANDAMENTO, detalhe)

    def concluir(self, etapa: Etapa, detalhe: str | None) -> None:
        self._informar(etapa, Estado.CONCLUIDA, detalhe)

    def falhar(self, etapa: Etapa, detalhe: str | None) -> None:
        self._informar(etapa, Estado.FALHOU, detalhe)

    def terminar_altura(self, d: Dado[list]) -> Dado[list]:
        com_altura = sum(1 for v in d.valor if v is not None) if d.disponivel else 0
        if com_altura == 0:
            self.falhar(Etapa.ALTURA, "o serviço de altitude não respondeu")
        else:
            self.concluir(Etapa.ALTURA, f"{com_altura}" + (" ponto analisado" if com_altura == 1
                                                           else " pontos analisados"))
        return d

    def terminar_setores(self, d: Dado[list[SetorRisco]]) -> Dado[list[SetorRisco]]:
        if not d.disponivel:
            self.falhar(Etapa.SETORES, "o serviço não respondeu; o caminho não vai desviar das áreas de risco")
            return d
        n = sum(1 for s in d.valor if s.hidrologico)
        self.concluir(Etapa.SETORES, "nenhuma área de risco de inundação mapeada" if n == 0 else
                      f"{n}" + (" área de risco de inundação encontrada" if n == 1
                                else " áreas de risco de inundação encontradas"))
        return d

    def verificar_cancelamento(self) -> None:
        """Para o cálculo se a pessoa desistiu, antes de mais uma consulta externa."""
        if self.progresso.cancelado():
            raise CalculoCancelado()

    def _informar(self, etapa: Etapa, estado: Estado, detalhe: str | None) -> None:
        try:
            self.progresso.informar(Evento(etapa.name, estado.value, etapa.rotulo, etapa.fonte, detalhe))
        except Exception as e:  # noqa: BLE001 - o andamento nunca derruba o cálculo
            log.debug("Falha ao informar andamento da rota: %s", e)


@dataclass
class Montador:
    """Acumula as partes da resposta."""

    modo: ModoRota
    andamento: Andamento
    avisos: list[str] = field(default_factory=list)
    fontes: list[str] = field(default_factory=list)
    setores: list[SetorMapa] = field(default_factory=list)
    destino: Destino | None = None
    trajeto: Trajeto | None = None
    perfil: Perfil | None = None

    def _avisos_finais(self) -> list[str]:
        return self.avisos + [
            "Esta é uma sugestão calculada automaticamente com dados públicos, não uma rota oficial de evacuação: "
            "a altura do terreno tem margem de erro de alguns metros e as ruas podem estar alagadas ou bloqueadas.",
            "Nunca atravesse ruas alagadas, a pé ou de carro. Siga sempre as orientações da Defesa Civil (199) "
            "e dos Bombeiros (193)."]

    def sem_rota(self, status: str, origem: Ponto, mensagem: str) -> RotaSeguraResponse:
        return RotaSeguraResponse(status=status, mensagem=mensagem, modo=self.modo.value, modo_rotulo=self.modo.rotulo,
                                  origem=origem, destino=self.destino, trajeto=None, perfil=None,
                                  setores_risco=self.setores, avisos=self._avisos_finais(),
                                  fontes=list(dict.fromkeys(self.fontes)), calculado_em=datetime.now(timezone.utc))

    def com_rota(self, origem: Ponto, mensagem: str) -> RotaSeguraResponse:
        return RotaSeguraResponse(status="ROTA_ENCONTRADA", mensagem=mensagem, modo=self.modo.value,
                                  modo_rotulo=self.modo.rotulo, origem=origem, destino=self.destino,
                                  trajeto=self.trajeto, perfil=self.perfil, setores_risco=self.setores,
                                  avisos=self._avisos_finais(), fontes=list(dict.fromkeys(self.fontes)),
                                  calculado_em=datetime.now(timezone.utc))
