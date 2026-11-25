"""Importa registros oficiais municipais (S2iD / Atlas Digital de Desastres) a partir da planilha
CSV baixada pelo administrador. Evita duplicidade pelo protocolo do registro."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from alertalar.erros import IntegracaoExterna
from alertalar.esquemas import ImportacaoResultado
from alertalar.integracoes.ibge import IbgeLocalidadesClient
from alertalar.integracoes.s2id import LeitorRegistrosOficiaisCsv, RegistroOficial
from alertalar.modelos.entidades import Ocorrencia, Usuario
from alertalar.modelos.enums import NivelLocalizacao, OrigemOcorrencia, StatusValidacao
from alertalar.repositorios import FonteDadosRepositorio, OcorrenciaRepositorio

log = logging.getLogger("alertalar.importacao")

FONTE_S2ID = "S2ID_RECONHECIMENTOS"


class ImportacaoService:
    def __init__(self, leitor: LeitorRegistrosOficiaisCsv, ocorrencias: OcorrenciaRepositorio,
                 fontes: FonteDadosRepositorio, ibge: IbgeLocalidadesClient):
        self.leitor = leitor
        self.ocorrencias = ocorrencias
        self.fontes = fontes
        self.ibge = ibge

    def importar_registros_oficiais(self, conteudo: bytes, nome_arquivo: str | None,
                                    administrador: Usuario | None) -> ImportacaoResultado:
        leitura = self.leitor.ler(conteudo)
        fonte = self.fontes.por_codigo(FONTE_S2ID)
        if fonte is None:
            raise RuntimeError(f"Fonte {FONTE_S2ID} não cadastrada")
        arquivo = "planilha" if nome_arquivo is None else re.sub(r"[^\w._ -]", "_", nome_arquivo)

        vistos: set[str] = set()
        estados: set[str] = set()
        novas: list[Ocorrencia] = []
        duplicados = sem_ibge = 0
        agora = datetime.now(timezone.utc)
        for r in leitura.registros:
            ident = identificador(r)
            if ident in vistos or self.ocorrencias.existe_identificador(fonte.id, ident):
                duplicados += 1
                continue
            vistos.add(ident)
            codigo_ibge = r.codigo_ibge if r.codigo_ibge is not None else self._buscar_ibge(r.uf, r.municipio)
            if codigo_ibge is None:
                sem_ibge += 1
            municipio = r.municipio if r.municipio is not None else f"Município IBGE {codigo_ibge}"
            novas.append(Ocorrencia(
                fonte_id=fonte.id, identificador_externo=ident, origem=OrigemOcorrencia.OFICIAL,
                status_validacao=StatusValidacao.CONFIRMADA, nivel_localizacao=NivelLocalizacao.MUNICIPIO,
                localizacao=f"Município de {municipio}/{r.uf} (registro municipal, sem endereço específico)",
                municipio=municipio, estado=r.uf, codigo_ibge=codigo_ibge, data_ocorrencia=r.data, tipo_evento=r.tipo,
                descricao=_descricao(r, arquivo), validado_por_id=None if administrador is None else administrador.id,
                data_validacao=agora, data_registro=agora))
            estados.add(r.uf)
        self.ocorrencias.salvar_todas(novas)
        if novas:
            fonte.data_atualizacao = datetime.now(timezone.utc)
            self.fontes.salvar(fonte)
        log.info("Importação de registros oficiais: %d novos, %d duplicados, arquivo %s", len(novas), duplicados, arquivo)
        return ImportacaoResultado(arquivo=arquivo, linhas_lidas=leitura.linhas_lidas, importados=len(novas),
                                   duplicados=duplicados, ignorados_nao_hidrologicos=leitura.ignoradas_nao_hidrologicas,
                                   invalidos=leitura.ignoradas_invalidas, sem_codigo_ibge=sem_ibge,
                                   estados=sorted(estados))

    def _buscar_ibge(self, uf: str, municipio: str | None) -> str | None:
        try:
            return self.ibge.codigo_municipio(uf, municipio)
        except IntegracaoExterna:
            return None


def _descricao(r: RegistroOficial, arquivo: str) -> str:
    texto = "Registro oficial de " + r.tipo.rotulo.lower()
    if r.cobrade is not None:
        texto += f" (COBRADE {r.cobrade})"
    if r.descricao_tipo is not None:
        texto += " - " + r.descricao_tipo
    if r.protocolo is not None:
        texto += ". Protocolo " + r.protocolo
    if r.somente_ano:
        texto += ". A fonte informa apenas o ano do evento"
    texto += f". Importado da planilha \"{arquivo}\" (S2iD/Atlas Digital - MIDR)."
    return texto[:1999] if len(texto) > 2000 else texto


def identificador(r: RegistroOficial) -> str:
    """Protocolo do S2iD, ou um hash estável dos campos quando a planilha não traz protocolo."""
    if r.protocolo is not None and r.protocolo.strip():
        return "PROT:" + r.protocolo.strip()
    base = "|".join((r.uf, _java_str(r.codigo_ibge), _java_str(r.municipio), r.data.isoformat(), r.tipo.value,
                     _java_str(r.cobrade)))
    return "HASH:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:40]


def _java_str(valor: str | None) -> str:
    # Mesmo texto da versão em Java (String.valueOf de null é "null"), para o hash não mudar
    return "null" if valor is None else valor
