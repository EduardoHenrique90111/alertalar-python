"""Monta os clientes externos, repositórios e serviços a partir das configurações (o papel que os
@Bean do Spring tinham na versão em Java)."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy import Engine

from alertalar.banco import FabricaSessoes, criar_engine, criar_fabrica
from alertalar.config import Configuracoes
from alertalar.integracoes.http import ClienteHttpExterno, LimitadorIntervalo
from alertalar.integracoes.ibge import IbgeLocalidadesClient, MunicipiosIbge
from alertalar.integracoes.nominatim import NominatimClient
from alertalar.integracoes.open_meteo import ClimaClient, ElevacaoClient
from alertalar.integracoes.overpass import OverpassClient
from alertalar.integracoes.photon import PhotonClient
from alertalar.integracoes.s2id import LeitorRegistrosOficiaisCsv
from alertalar.integracoes.sgb import SgbSetoresRiscoClient
from alertalar.integracoes.valhalla import ValhallaClient
from alertalar.integracoes.viacep import ViaCepClient
from alertalar.modelos.enums import PapelUsuario
from alertalar.repositorios import (
    ConsultaRepositorio,
    EnderecoRepositorio,
    FonteDadosRepositorio,
    OcorrenciaRepositorio,
    UsuarioRepositorio,
)
from alertalar.servicos.analise.analise_risco import AnaliseRiscoService
from alertalar.servicos.analise.fatores import fatores_padrao
from alertalar.servicos.coleta import ColetaDadosService
from alertalar.servicos.consultas import ConsultaService
from alertalar.servicos.enderecos import EnderecoService
from alertalar.servicos.fontes import FonteDadosService
from alertalar.servicos.geocodificacao import GeocodificacaoService
from alertalar.servicos.importacao import ImportacaoService
from alertalar.servicos.ocorrencias import OcorrenciaService
from alertalar.servicos.rota_segura import RotaSeguraService
from alertalar.servicos.situacao_atual import SituacaoAtualService
from alertalar.servicos.usuarios import UsuarioService
from alertalar.util import texto as txt

log = logging.getLogger("alertalar")


@dataclass
class Servicos:
    config: Configuracoes
    engine: Engine
    sessoes: FabricaSessoes
    fontes: FonteDadosService
    usuarios: UsuarioService
    enderecos: EnderecoService
    coleta: ColetaDadosService
    consultas: ConsultaService
    ocorrencias: OcorrenciaService
    importacao: ImportacaoService
    situacao_atual: SituacaoAtualService
    rotas: RotaSeguraService
    # Cálculos de rota acompanhados pela tela (um por pessoa esperando)
    executor_rotas: ThreadPoolExecutor

    def encerrar(self) -> None:
        self.executor_rotas.shutdown(wait=False, cancel_futures=True)
        self.coleta.encerrar()
        self.rotas.encerrar()
        self.engine.dispose()


def montar(config: Configuracoes, engine: Engine | None = None, municipios: MunicipiosIbge | None = None,
           custo_bcrypt: int | None = None) -> Servicos:
    engine = engine or criar_engine(config.url_banco, config.db_pool)
    sessoes = criar_fabrica(engine)
    i = config.integracoes
    http = ClienteHttpExterno(config.user_agent, i.timeout_conexao, i.timeout_leitura)

    via_cep = ViaCepClient(http, i.viacep_url)
    nominatim = NominatimClient(http, i.nominatim_url, config.contato_email,
                                LimitadorIntervalo(i.nominatim_intervalo_minimo))
    # Reserva do Nominatim (mesmos dados do OpenStreetMap, outro servidor)
    photon = PhotonClient(http, i.photon_url, LimitadorIntervalo(i.photon_intervalo_minimo))
    ibge = IbgeLocalidadesClient(http, i.ibge_url)
    overpass = OverpassClient(http, i.overpass_url)
    elevacao = ElevacaoClient(http, i.elevacao_url)
    clima = ClimaClient(http, i.previsao_url, i.vazao_url)
    sgb = SgbSetoresRiscoClient(http, i.sgb_setores_risco_url)
    valhalla = ValhallaClient(http, i.rotas_url, i.rotas_chave_api, LimitadorIntervalo(i.rotas_intervalo_minimo))

    repo_fontes = FonteDadosRepositorio(sessoes)
    repo_ocorrencias = OcorrenciaRepositorio(sessoes)
    repo_consultas = ConsultaRepositorio(sessoes)
    fontes = FonteDadosService(repo_fontes)
    usuarios = UsuarioService(UsuarioRepositorio(sessoes), **({} if custo_bcrypt is None else {"custo_bcrypt": custo_bcrypt}))
    enderecos = EnderecoService(via_cep, GeocodificacaoService(nominatim, photon, fontes), ibge,
                                municipios if municipios is not None else MunicipiosIbge.carregar(),
                                EnderecoRepositorio(sessoes), fontes)
    coleta = ColetaDadosService(overpass, elevacao, sgb, repo_ocorrencias, fontes, config.analise)
    return Servicos(
        config=config, engine=engine, sessoes=sessoes, fontes=fontes, usuarios=usuarios, enderecos=enderecos,
        coleta=coleta,
        consultas=ConsultaService(enderecos, coleta, AnaliseRiscoService(fatores_padrao()), repo_consultas, fontes),
        ocorrencias=OcorrenciaService(repo_ocorrencias, fontes, ibge, coleta),
        importacao=ImportacaoService(LeitorRegistrosOficiaisCsv(), repo_ocorrencias, repo_fontes, ibge),
        situacao_atual=SituacaoAtualService(clima, fontes, repo_consultas),
        rotas=RotaSeguraService(elevacao, sgb, valhalla, fontes),
        executor_rotas=ThreadPoolExecutor(max_workers=32, thread_name_prefix="rota-progresso"),
    )


def criar_admin_inicial(servicos: Servicos) -> None:
    """Cria o primeiro administrador a partir de ALERTALAR_ADMIN_EMAIL e ALERTALAR_ADMIN_SENHA.
    Não existe senha padrão embutida no código."""
    admin = servicos.config.admin
    if txt.vazio(admin.email) or txt.vazio(admin.senha):
        log.info("Nenhum administrador configurado (ALERTALAR_ADMIN_EMAIL / ALERTALAR_ADMIN_SENHA). "
                 "A moderação de relatos ficará indisponível até que um seja configurado.")
        return
    if len(admin.senha) < 10 or not re.search(r"[A-Za-z]", admin.senha) or not re.search(r"\d", admin.senha):
        log.error("ALERTALAR_ADMIN_SENHA fraca: use ao menos 10 caracteres com letras e números. "
                  "Administrador não criado.")
        return
    existente = servicos.usuarios.por_email(admin.email)
    if existente is None:
        servicos.usuarios.criar(admin.nome, admin.email, admin.senha, PapelUsuario.ADMIN)
        log.info("Administrador inicial criado para %s", admin.email)
    elif existente.papel != PapelUsuario.ADMIN:
        log.warning("O e-mail de administrador configurado pertence a uma conta comum; ela NÃO foi promovida "
                    "automaticamente.")
