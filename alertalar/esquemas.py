from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from alertalar.erros import DadosInvalidos
from alertalar.modelos.enums import StatusValidacao, TipoEvento
from alertalar.util import uf as ufs

T = TypeVar("T")


def camel(nome: str) -> str:
    primeira, *resto = nome.split("_")
    return primeira + "".join(p[:1].upper() + p[1:] for p in resto)


class Esquema(BaseModel):
    model_config = ConfigDict(alias_generator=camel, populate_by_name=True, serialize_by_alias=True)


class Pedido(Esquema):
    model_config = ConfigDict(alias_generator=camel, populate_by_name=True, coerce_numbers_to_str=True,
                              extra="ignore")


_EMAIL_LOCAL = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~\u0080-￿-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~\u0080-￿-]+)*"
_EMAIL_ROTULO = r"[A-Za-z0-9\u0080-￿](?:[A-Za-z0-9\u0080-￿-]*[A-Za-z0-9\u0080-￿])?"
_EMAIL = re.compile(rf"(?:{_EMAIL_LOCAL})@(?:{_EMAIL_ROTULO}(?:\.{_EMAIL_ROTULO})*|\[[0-9.:A-Fa-f]+\])")


def email_valido(valor: str | None) -> bool:
    if not valor:
        return True
    if _EMAIL.fullmatch(valor) is None:
        return False
    return len(valor.rsplit("@", 1)[0]) <= 64


class Erros:
    def __init__(self) -> None:
        self.mapa: dict[str, str] = {}

    def exigir(self, campo: str, ok: bool, mensagem: str) -> None:
        if not ok and campo not in self.mapa:
            self.mapa[campo] = mensagem

    def lancar_se_houver(self) -> None:
        if self.mapa:
            raise DadosInvalidos(self.mapa)


def _em_branco(v: str | None) -> bool:
    return v is None or v.strip() == ""


def _no_brasil(erros: Erros, latitude: float | None, longitude: float | None) -> None:
    erros.exigir("latitude", latitude is None or -34.0 <= latitude <= 5.5,
                 "A latitude deve estar dentro do território brasileiro.")
    erros.exigir("longitude", longitude is None or -74.2 <= longitude <= -28.6,
                 "A longitude deve estar dentro do território brasileiro.")
    erros.exigir("coordenadasCompletas", (latitude is None) == (longitude is None),
                 "Informe latitude e longitude juntas, ou nenhuma das duas.")


class EnderecoRequest(Pedido):
    cep: str | None = None
    rua: str | None = None
    numero: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    estado: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def possui_coordenadas(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def validar(self) -> EnderecoRequest:
        e = Erros()
        e.exigir("cep", self.cep is None or re.fullmatch(r"(\d{5}-?\d{3})?", self.cep, re.ASCII) is not None,
                 "O CEP deve ter 8 dígitos (ex.: 92010-000).")
        e.exigir("rua", not _em_branco(self.rua), "Informe a rua ou avenida.")
        e.exigir("rua", self.rua is None or len(self.rua) <= 200, "A rua deve ter no máximo 200 caracteres.")
        e.exigir("numero", self.numero is None or len(self.numero) <= 20, "O número deve ter no máximo 20 caracteres.")
        e.exigir("numero", self.numero is None or re.fullmatch(r"[0-9A-Za-z/ -]*", self.numero) is not None,
                 "Número inválido. Use apenas números, letras, \"/\" ou \"-\".")
        e.exigir("bairro", self.bairro is None or len(self.bairro) <= 120, "O bairro deve ter no máximo 120 caracteres.")
        e.exigir("cidade", not _em_branco(self.cidade), "Informe a cidade.")
        e.exigir("cidade", self.cidade is None or len(self.cidade) <= 120, "A cidade deve ter no máximo 120 caracteres.")
        e.exigir("estado", not _em_branco(self.estado), "Informe o estado (UF).")
        e.exigir("estado", self.estado is None or ufs.sigla_valida(self.estado),
                 "Estado inválido. Use a sigla da UF, ex.: RS.")
        _no_brasil(e, self.latitude, self.longitude)
        e.lancar_se_houver()
        return self


class OcorrenciaRequest(Pedido):
    localizacao: str | None = None
    municipio: str | None = None
    estado: str | None = None
    data_ocorrencia: date | None = None
    descricao: str | None = None
    tipo_evento: TipoEvento | None = None
    latitude: float | None = None
    longitude: float | None = None
    nome_relator: str | None = None
    contato_relator: str | None = None
    declaracao_veracidade: bool | None = None

    def validar(self, hoje: date | None = None) -> OcorrenciaRequest:
        hoje = hoje or date.today()
        e = Erros()
        e.exigir("localizacao", not _em_branco(self.localizacao), "Informe o local da ocorrência.")
        e.exigir("localizacao", self.localizacao is None or 5 <= len(self.localizacao) <= 300,
                 "O local deve ter entre 5 e 300 caracteres.")
        e.exigir("municipio", not _em_branco(self.municipio), "Informe o município.")
        e.exigir("municipio", self.municipio is None or len(self.municipio) <= 120,
                 "O município deve ter no máximo 120 caracteres.")
        e.exigir("estado", not _em_branco(self.estado), "Informe o estado (UF).")
        e.exigir("estado", self.estado is None or ufs.sigla_valida(self.estado),
                 "Estado inválido. Use a sigla da UF, ex.: RS.")
        e.exigir("dataOcorrencia", self.data_ocorrencia is not None, "Informe a data da ocorrência.")
        e.exigir("dataOcorrencia", self.data_ocorrencia is None or self.data_ocorrencia <= hoje,
                 "A data da ocorrência não pode estar no futuro.")
        e.exigir("descricao", not _em_branco(self.descricao), "Descreva o que aconteceu.")
        e.exigir("descricao", self.descricao is None or 10 <= len(self.descricao) <= 2000,
                 "A descrição deve ter entre 10 e 2000 caracteres.")
        e.exigir("tipoEvento", self.tipo_evento is not None, "Informe o tipo de evento.")
        _no_brasil(e, self.latitude, self.longitude)
        e.exigir("nomeRelator", self.nome_relator is None or len(self.nome_relator) <= 120,
                 "O nome deve ter no máximo 120 caracteres.")
        e.exigir("contatoRelator", email_valido(self.contato_relator), "E-mail de contato inválido.")
        e.exigir("contatoRelator", self.contato_relator is None or len(self.contato_relator) <= 254,
                 "O e-mail deve ter no máximo 254 caracteres.")
        e.exigir("declaracaoVeracidade", self.declaracao_veracidade is True,
                 "Confirme que as informações são verdadeiras.")
        e.exigir("dataPlausivel", self.data_ocorrencia is None or self.data_ocorrencia.year >= 1900,
                 "A data da ocorrência deve ser posterior a 1900.")
        e.lancar_se_houver()
        return self


_SENHA = re.compile(r"(?=.*[A-Za-z])(?=.*\d).+", re.ASCII)


class RegistroRequest(Pedido):
    nome: str | None = None
    email: str | None = None
    senha: str | None = None

    def validar(self) -> RegistroRequest:
        e = Erros()
        e.exigir("nome", not _em_branco(self.nome), "Informe seu nome.")
        e.exigir("nome", self.nome is None or len(self.nome) <= 120, "O nome deve ter no máximo 120 caracteres.")
        e.exigir("email", not _em_branco(self.email), "Informe seu e-mail.")
        e.exigir("email", email_valido(self.email), "E-mail inválido.")
        e.exigir("email", self.email is None or len(self.email) <= 254, "O e-mail deve ter no máximo 254 caracteres.")
        e.exigir("senha", not _em_branco(self.senha), "Informe uma senha.")
        e.exigir("senha", self.senha is None or 8 <= len(self.senha) <= 72, "A senha deve ter entre 8 e 72 caracteres.")
        e.exigir("senha", self.senha is None or _SENHA.fullmatch(self.senha) is not None,
                 "A senha deve conter letras e números.")
        e.lancar_se_houver()
        return self


class LoginRequest(Pedido):
    email: str | None = None
    senha: str | None = None

    def validar(self) -> LoginRequest:
        e = Erros()
        e.exigir("email", not _em_branco(self.email), "Informe seu e-mail.")
        e.exigir("email", email_valido(self.email), "E-mail inválido.")
        e.exigir("senha", not _em_branco(self.senha), "Informe sua senha.")
        e.exigir("senha", self.senha is None or len(self.senha) <= 72, "Senha inválida.")
        e.lancar_se_houver()
        return self


class ValidacaoRequest(Pedido):
    status: StatusValidacao | None = None
    observacao: str | None = None

    def validar(self) -> ValidacaoRequest:
        e = Erros()
        e.exigir("status", self.status is not None, "Informe o novo status (CONFIRMADA ou REJEITADA).")
        e.exigir("observacao", self.observacao is None or len(self.observacao) <= 500,
                 "A observação deve ter no máximo 500 caracteres.")
        e.lancar_se_houver()
        return self


class UsuarioResponse(Esquema):
    id: int
    nome: str
    email: str
    papel: str


class CepResponse(Esquema):
    cep: str | None
    rua: str | None
    bairro: str | None
    cidade: str | None
    estado: str | None
    codigo_ibge: str | None
    fonte: str


class Candidato(Esquema):
    latitude: float
    longitude: float
    precisao: str
    descricao_precisao: str
    suficiente_para_analise: bool
    endereco_encontrado: str | None
    fonte: str | None


class LocalizacaoResponse(Esquema):
    candidatos: list[Candidato]
    mensagem: str


class EnderecoResponse(Esquema):
    descricao: str
    cep: str | None
    rua: str | None
    numero: str | None
    bairro: str | None
    cidade: str
    estado: str
    codigo_ibge: str | None
    latitude: float
    longitude: float
    precisao: str
    descricao_precisao: str
    fonte_geocodificacao: str | None


class FatorResponse(Esquema):
    codigo: str
    nome: str
    categoria: str
    situacao: str
    pontuacao: int | None
    peso: float
    valor_observado: str | None
    explicacao: str
    fonte_codigo: str | None
    fonte_nome: str | None
    data_referencia: datetime | None


class FonteResponse(Esquema):
    codigo: str
    nome: str
    tipo: str
    url: str | None
    status_integracao: str
    oficial: bool
    data_atualizacao: datetime | None
    descricao: str | None
    atribuicao: str | None


class OcorrenciaResponse(Esquema):
    id: int | None
    localizacao: str
    municipio: str | None
    estado: str | None
    data_ocorrencia: date
    descricao: str
    tipo_evento: str
    tipo_evento_rotulo: str
    origem: str
    origem_rotulo: str
    nivel_localizacao: str
    latitude: float | None
    longitude: float | None
    fonte: str | None
    distancia_metros: float | None
    data_registro: datetime | None


class OcorrenciaAdminResponse(Esquema):
    ocorrencia: OcorrenciaResponse
    status_validacao: str
    nome_relator: str | None
    contato_relator: str | None
    observacao_validacao: str | None
    data_validacao: datetime | None


class PaginaResponse(Esquema, Generic[T]):
    itens: list[T]
    pagina: int
    tamanho: int
    total: int
    total_paginas: int


class DimensaoResponse(Esquema):
    categoria: str
    titulo: str
    descricao: str
    nivel: str
    rotulo_nivel: str


class HistoricoMunicipalResponse(Esquema):
    municipio_identificado: bool
    base_importada: bool
    total: int
    registros: list[OcorrenciaResponse]


class ConsultaResponse(Esquema):
    id: uuid.UUID
    data_consulta: datetime
    endereco: EnderecoResponse
    classificacao: str
    rotulo: str
    resumo: str
    indice: float | None
    justificativa: str
    versao_metodologia: str
    dimensoes: list[DimensaoResponse]
    fatores: list[FatorResponse]
    ocorrencias_proximas: list[OcorrenciaResponse]
    historico_municipal: HistoricoMunicipalResponse
    mapa: Any
    fontes: list[FonteResponse]
    avisos: list[str]


class ConsultaResumo(Esquema):
    id: uuid.UUID
    data_consulta: datetime
    endereco: str
    classificacao: str
    rotulo: str


class ImportacaoResultado(Esquema):
    arquivo: str
    linhas_lidas: int
    importados: int
    duplicados: int
    ignorados_nao_hidrologicos: int
    invalidos: int
    sem_codigo_ibge: int
    estados: list[str]


class RiscoAgora(Esquema):
    nivel: str
    rotulo: str
    nivel_chuva: int | None
    nivel_chuva_rotulo: str | None
    suscetibilidade: str | None
    resumo: str
    motivos: list[str]
    proximos_dias: str | None
    criterio: str


class Chuva(Esquema):
    disponivel: bool
    motivo: str | None
    ultimas_24h_mm: float | None
    ultimas_72h_mm: float | None
    maior_intensidade_horaria_ultimas_24h_mm: float | None
    proximas_24h_mm: float | None
    proximas_72h_mm: float | None
    maior_intensidade_horaria_proximas_24h_mm: float | None
    maior_24h_entre_24e72h_mm: float | None
    fonte: str

    @classmethod
    def indisponivel(cls, motivo: str | None, fonte: str) -> Chuva:
        return cls(disponivel=False, motivo=motivo, ultimas_24h_mm=None, ultimas_72h_mm=None,
                   maior_intensidade_horaria_ultimas_24h_mm=None, proximas_24h_mm=None, proximas_72h_mm=None,
                   maior_intensidade_horaria_proximas_24h_mm=None, maior_24h_entre_24e72h_mm=None, fonte=fonte)


class Vazao(Esquema):
    disponivel: bool
    motivo: str | None
    hoje_m3s: float | None
    sete_dias_atras_m3s: float | None
    maxima_prevista_7_dias_m3s: float | None
    tendencia: str | None
    fonte: str
    observacao: str


class SituacaoAtualResponse(Esquema):
    latitude: float
    longitude: float
    risco_agora: RiscoAgora
    chuva: Chuva
    vazao: Vazao
    avisos: list[str]
    consultado_em: datetime


class Ponto(Esquema):
    latitude: float
    longitude: float
    elevacao: float | None


class Destino(Esquema):
    latitude: float
    longitude: float
    elevacao: float | None
    ganho_elevacao: float | None
    distancia_reta_metros: float
    descricao: str


class InstrucaoRota(Esquema):
    texto: str
    distancia_metros: float
    duracao_segundos: float


class Trajeto(Esquema):
    distancia_metros: float
    duracao_segundos: float
    coordenadas: list[tuple[float, float]]
    instrucoes: list[InstrucaoRota]
    desvio_areas_risco_aplicado: bool
    setores_evitados: int


class Perfil(Esquema):
    elevacao_minima: float
    elevacao_maxima: float
    distancia_ponto_mais_baixo: float
    ponto_mais_baixo: tuple[float, float]
    amostras: list[tuple[float, float]]


class SetorMapa(Esquema):
    numero: str | None
    grau: str | None
    tipologia: str | None
    aneis: list[list[tuple[float, float]]]


class RotaSeguraResponse(Esquema):
    status: str
    mensagem: str
    modo: str
    modo_rotulo: str
    origem: Ponto
    destino: Destino | None
    trajeto: Trajeto | None
    perfil: Perfil | None
    setores_risco: list[SetorMapa]
    avisos: list[str]
    fontes: list[str]
    calculado_em: datetime
