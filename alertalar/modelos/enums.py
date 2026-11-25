"""Enumerações gravadas no banco pelo nome (VARCHAR com CHECK nas tabelas)."""

from __future__ import annotations

from enum import Enum


class _EnumTexto(str, Enum):
    """Enum cujo valor é o próprio nome (assim vai para o JSON e para o banco)."""

    def __str__(self) -> str:
        return self.value


class CategoriaFator(_EnumTexto):
    # Áreas de risco mapeadas por órgão oficial (ex.: SGB)
    RISCO_MAPEADO = "RISCO_MAPEADO"
    # Características do terreno: proximidade de água e elevação relativa
    SUSCETIBILIDADE = "SUSCETIBILIDADE"
    # Ocorrências registradas no passado
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
    # O número do imóvel foi encontrado
    NUMERO = "NUMERO"
    # Apenas a rua foi encontrada: o ponto representa a via, não necessariamente o imóvel
    RUA = "RUA"
    # Posição confirmada ou ajustada pelo usuário no mapa
    MANUAL = "MANUAL"

    @property
    def descricao(self) -> str:
        return {"NUMERO": "Número do imóvel localizado", "RUA": "Localização aproximada pela rua",
                "MANUAL": "Posição confirmada no mapa pelo usuário"}[self.value]

    @property
    def ordem(self) -> int:
        return list(PrecisaoGeocodificacao).index(self)


class SituacaoFator(_EnumTexto):
    # O fator foi calculado com dados reais e entrou na média ponderada
    AVALIADO = "AVALIADO"
    # A fonte respondeu, mas não há registro; a ausência não é tratada como evidência de baixo risco
    SEM_REGISTRO = "SEM_REGISTRO"
    # A fonte não estava disponível ou não cobre a região
    INDISPONIVEL = "INDISPONIVEL"


class StatusIntegracao(_EnumTexto):
    # Integração implementada e consultada pelo sistema
    ATIVA = "ATIVA"
    # Dados oficiais carregados por importação de arquivo feita pelo administrador
    IMPORTACAO_MANUAL = "IMPORTACAO_MANUAL"
    # Fonte exige cadastro/credencial; integração ainda não implementada
    REQUER_CREDENCIAL = "REQUER_CREDENCIAL"
    # Integração prevista, ainda não implementada
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
