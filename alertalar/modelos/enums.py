from __future__ import annotations

from enum import Enum


class _EnumTexto(str, Enum):
    def __str__(self) -> str:
        return self.value


class CategoriaFator(_EnumTexto):
    RISCO_MAPEADO = "RISCO_MAPEADO"
    SUSCETIBILIDADE = "SUSCETIBILIDADE"
    HISTORICO = "HISTORICO"


class ClassificacaoRisco(_EnumTexto):
    BAIXO = "BAIXO"
    MODERADO = "MODERADO"
    ALTO = "ALTO"
    DADOS_INSUFICIENTES = "DADOS_INSUFICIENTES"

    @property
    def rotulo(self) -> str:
        return {"BAIXO": "Baixo risco", "MODERADO": "Risco moderado", "ALTO": "Alto risco",
                "DADOS_INSUFICIENTES": "Dados insuficientes"}[self.value]


class NivelLocalizacao(_EnumTexto):
    PONTO = "PONTO"
    MUNICIPIO = "MUNICIPIO"


class OrigemOcorrencia(_EnumTexto):
    OFICIAL = "OFICIAL"
    RELATO_USUARIO = "RELATO_USUARIO"


class PapelUsuario(_EnumTexto):
    USUARIO = "USUARIO"
    ADMIN = "ADMIN"


class PrecisaoGeocodificacao(_EnumTexto):
    NUMERO = "NUMERO"
    RUA = "RUA"
    MANUAL = "MANUAL"

    @property
    def descricao(self) -> str:
        return {"NUMERO": "Número do imóvel localizado", "RUA": "Localização aproximada pela rua",
                "MANUAL": "Posição confirmada no mapa pelo usuário"}[self.value]

    @property
    def ordem(self) -> int:
        return list(PrecisaoGeocodificacao).index(self)


class SituacaoFator(_EnumTexto):
    AVALIADO = "AVALIADO"
    SEM_REGISTRO = "SEM_REGISTRO"
    INDISPONIVEL = "INDISPONIVEL"


class StatusIntegracao(_EnumTexto):
    ATIVA = "ATIVA"
    IMPORTACAO_MANUAL = "IMPORTACAO_MANUAL"
    REQUER_CREDENCIAL = "REQUER_CREDENCIAL"
    PLANEJADA = "PLANEJADA"


class StatusValidacao(_EnumTexto):
    PENDENTE = "PENDENTE"
    CONFIRMADA = "CONFIRMADA"
    REJEITADA = "REJEITADA"


class TipoEvento(_EnumTexto):
    ALAGAMENTO = "ALAGAMENTO"
    INUNDACAO = "INUNDACAO"
    ENXURRADA = "ENXURRADA"
    CHUVA_INTENSA = "CHUVA_INTENSA"
    OUTRO = "OUTRO"

    @property
    def rotulo(self) -> str:
        return {"ALAGAMENTO": "Alagamento", "INUNDACAO": "Inundação", "ENXURRADA": "Enxurrada",
                "CHUVA_INTENSA": "Chuvas intensas", "OUTRO": "Outro evento relacionado a chuvas"}[self.value]


class TipoFonte(_EnumTexto):
    API_EXTERNA = "API_EXTERNA"
    BASE_GEOGRAFICA = "BASE_GEOGRAFICA"
    IMPORTACAO_OFICIAL = "IMPORTACAO_OFICIAL"
    RELATO_USUARIO = "RELATO_USUARIO"
