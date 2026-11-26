from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from alertalar.erros import ArquivoInvalido
from alertalar.modelos.enums import TipoEvento
from alertalar.util import texto as txt

ALIASES: dict[str, list[str]] = {
    "ibge": ["cod_ibge_mun", "codigo_ibge", "cod_ibge", "ibge", "cod_municipio", "codigo_municipio", "geocodigo",
             "cod_ibge_municipio", "codigo_ibge_municipio", "cd_geocmu"],
    "municipio": ["municipio", "nome_municipio", "nome_do_municipio", "cidade", "municipio_uf"],
    "uf": ["uf", "sigla_uf", "estado", "sigla_estado"],
    "data": ["data_evento", "data_do_evento", "data_ocorrencia", "data_da_ocorrencia", "data_desastre",
             "data_do_desastre", "dt_evento", "data"],
    "ano": ["ano", "ano_evento", "ano_ocorrencia", "ano_do_evento"],
    "cobrade": ["cobrade", "cod_cobrade", "codigo_cobrade", "cobrade_codigo"],
    "tipo": ["desastre", "tipologia", "tipo_desastre", "tipo_de_desastre", "descricao_tipologia", "evento",
             "descricao_cobrade", "subgrupo", "grupo_de_desastre"],
    "protocolo": ["protocolo", "protocolo_s2id", "numero_protocolo", "n_protocolo", "registro", "id"],
}


@dataclass(frozen=True)
class RegistroOficial:
    protocolo: str | None
    uf: str
    municipio: str | None
    codigo_ibge: str | None
    data: date
    somente_ano: bool
    tipo: TipoEvento
    cobrade: str | None
    descricao_tipo: str | None


@dataclass(frozen=True)
class ResultadoLeitura:
    registros: list[RegistroOficial]
    linhas_lidas: int
    ignoradas_nao_hidrologicas: int
    ignoradas_invalidas: int


class LeitorRegistrosOficiaisCsv:
    def ler(self, conteudo: bytes | None) -> ResultadoLeitura:
        if not conteudo:
            raise ArquivoInvalido("O arquivo enviado está vazio.")
        linhas = registros(decodificar(conteudo))
        if len(linhas) < 2:
            raise ArquivoInvalido("O arquivo não contém linhas de dados.")
        separador = detectar_separador(linhas[0])
        cabecalho = dividir(linhas[0], separador)
        colunas = mapear_colunas(cabecalho)
        if "uf" not in colunas or not ("municipio" in colunas or "ibge" in colunas):
            raise ArquivoInvalido("Colunas obrigatórias não encontradas: é preciso ter UF e Município "
                                  "(ou código IBGE). Colunas lidas: " + ", ".join(cabecalho))
        if "data" not in colunas and "ano" not in colunas:
            raise ArquivoInvalido("Coluna de data do evento não encontrada (ex.: \"Data do Evento\").")
        if "cobrade" not in colunas and "tipo" not in colunas:
            raise ArquivoInvalido("Coluna do tipo de desastre não encontrada (ex.: \"COBRADE\" ou \"Desastre\").")

        lidos: list[RegistroOficial] = []
        nao_hidrologicas = invalidas = 0
        for linha in linhas[1:]:
            campos = dividir(linha, separador)

            def valor(chave: str) -> str | None:
                return _valor(campos, colunas, chave)

            tipo = classificar(valor("cobrade"), valor("tipo"))
            if tipo is None:
                nao_hidrologicas += 1
                continue
            uf = valor("uf")
            uf = uf.upper() if uf is not None else None
            municipio = valor("municipio")
            ibge = txt.somente_digitos(valor("ibge"))
            data = _ler_data(valor("data"), valor("ano"))
            if uf is None or len(uf) != 2 or data is None or (municipio is None and len(ibge) != 7):
                invalidas += 1
                continue
            if municipio is not None and "/" in municipio and re.search(r"/[A-Za-z]{2}$", municipio):
                municipio = municipio[:municipio.rfind("/")].strip()
            lidos.append(RegistroOficial(valor("protocolo"), uf, municipio, ibge if len(ibge) == 7 else None,
                                         data[0], data[1], tipo, valor("cobrade"), valor("tipo")))
        return ResultadoLeitura(lidos, len(linhas) - 1, nao_hidrologicas, invalidas)


def classificar(cobrade: str | None, descricao: str | None) -> TipoEvento | None:
    codigo = txt.somente_digitos(cobrade)
    if codigo.startswith("121"):
        return TipoEvento.INUNDACAO
    if codigo.startswith("122"):
        return TipoEvento.ENXURRADA
    if codigo.startswith("123"):
        return TipoEvento.ALAGAMENTO
    if codigo.startswith("13214"):
        return TipoEvento.CHUVA_INTENSA
    d = txt.normalizar(descricao)
    if "inunda" in d:
        return TipoEvento.INUNDACAO
    if "enxurr" in d:
        return TipoEvento.ENXURRADA
    if "alaga" in d:
        return TipoEvento.ALAGAMENTO
    if "chuvas intensas" in d or "chuva intensa" in d:
        return TipoEvento.CHUVA_INTENSA
    return None


_FORMATOS_DATA = (
    (re.compile(r"\d{2}/\d{2}/\d{4}"), "%d/%m/%Y"),
    (re.compile(r"\d{1,2}/\d{1,2}/\d{4}"), "%d/%m/%Y"),
    (re.compile(r"\d{4}-\d{2}-\d{2}"), "%Y-%m-%d"),
    (re.compile(r"\d{2}-\d{2}-\d{4}"), "%d-%m-%Y"),
)


def _ler_data(texto: str | None, ano: str | None) -> tuple[date, bool] | None:
    if texto is not None:
        t = texto.strip()
        if len(t) > 10 and t[10] in (" ", "T"):
            t = t[:10]
        for padrao, formato in _FORMATOS_DATA:
            if padrao.fullmatch(t):
                try:
                    return datetime.strptime(t, formato).date(), False
                except ValueError:
                    pass
    a = txt.somente_digitos(ano)
    if len(a) == 4:
        valor = int(a)
        if 1900 <= valor <= date.today().year:
            return date(valor, 1, 1), True
    return None


def _valor(campos: list[str], colunas: dict[str, int], chave: str) -> str | None:
    idx = colunas.get(chave)
    if idx is None or idx >= len(campos):
        return None
    return txt.limpar(campos[idx])


def registros(texto: str) -> list[str]:
    resultado = []
    atual: list[str] = []
    aspas = 0
    for linha in re.split(r"\r?\n", texto):
        atual.append(linha)
        aspas += linha.count('"')
        if aspas % 2 == 0:
            juntas = "\n".join(atual)
            if juntas.strip():
                resultado.append(juntas)
            atual = []
            aspas = 0
    juntas = "\n".join(atual)
    if juntas.strip():
        resultado.append(juntas)
    return resultado


def mapear_colunas(cabecalho: list[str]) -> dict[str, int]:
    normalizado: dict[str, int] = {}
    for i, nome in enumerate(cabecalho):
        n = re.sub(r"^_|_$", "", re.sub(r"[^a-z0-9]+", "_", txt.normalizar(nome)))
        normalizado.setdefault(n, i)
    colunas = {}
    for chave, nomes in ALIASES.items():
        for nome in nomes:
            if nome in normalizado:
                colunas[chave] = normalizado[nome]
                break
    return colunas


def detectar_separador(cabecalho: str) -> str:
    pv = cabecalho.count(";")
    vg = cabecalho.count(",")
    tab = cabecalho.count("\t")
    if tab > pv and tab > vg:
        return "\t"
    return ";" if pv >= vg else ","


def dividir(linha: str, separador: str) -> list[str]:
    campos = []
    atual: list[str] = []
    entre_aspas = False
    i = 0
    while i < len(linha):
        c = linha[i]
        if c == '"':
            if entre_aspas and i + 1 < len(linha) and linha[i + 1] == '"':
                atual.append('"')
                i += 1
            else:
                entre_aspas = not entre_aspas
        elif c == separador and not entre_aspas:
            campos.append("".join(atual))
            atual = []
        else:
            atual.append(c)
        i += 1
    campos.append("".join(atual))
    return campos


def decodificar(dados: bytes) -> str:
    inicio = 3 if dados[:3] == b"\xef\xbb\xbf" else 0
    try:
        return dados[inicio:].decode("utf-8")
    except UnicodeDecodeError:
        return dados[inicio:].decode("cp1252", errors="replace")
