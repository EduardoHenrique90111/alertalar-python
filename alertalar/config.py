from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

PADRAO_DB_URL = "postgresql://alertalar@localhost:5432/alertalar"


class ConfiguracaoInvalida(ValueError):
    pass


def ler_env(caminhos: list[Path] | None = None) -> dict[str, str]:
    valores: dict[str, str] = {}
    for caminho in caminhos if caminhos is not None else [Path("../.env"), Path(".env")]:
        if caminho.is_file():
            valores.update(_ler_arquivo_env(caminho))
    valores.update(os.environ)
    return valores


def _ler_arquivo_env(caminho: Path) -> dict[str, str]:
    valores = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip()
    return valores


def converter_database_url(valor: str) -> dict[str, str]:
    texto = valor.strip()
    if texto.lower().startswith("export "):
        texto = texto[len("export "):].strip()
    if texto.upper().startswith("DATABASE_URL="):
        texto = texto[len("DATABASE_URL="):].strip()
    if texto.startswith("psql "):
        texto = texto[5:].strip()
    texto = texto.strip("'\"")
    texto = "".join(texto.split())
    if texto.startswith("jdbc:postgresql://"):
        return {"DB_URL": texto}
    try:
        partes = urlsplit(texto)
        porta = partes.port
    except ValueError:
        return {}
    if partes.scheme not in ("postgresql", "postgres"):
        return {}
    if not partes.hostname or "@" not in partes.netloc:
        return {}
    banco = partes.path[1:] if partes.path and len(partes.path) > 1 else "postgres"
    sslmode = "require"
    for parte in (partes.query or "").split("&"):
        if parte.startswith("sslmode="):
            sslmode = parte[len("sslmode="):]
    host = partes.netloc.rsplit("@", 1)[1]
    host = host if porta is None else host.rsplit(":", 1)[0]
    resultado = {"DB_URL": f"postgresql://{host}{'' if porta is None else ':' + str(porta)}/{banco}?sslmode={sslmode}"}
    credenciais = partes.netloc.rsplit("@", 1)[0].split(":", 1)
    resultado["DB_USERNAME"] = _decodificar(credenciais[0])
    if len(credenciais) == 2:
        resultado["DB_PASSWORD"] = _decodificar(credenciais[1])
    return resultado


def problema_database_url(valor: str) -> str | None:
    formato = ("Ela deve ter o formato postgresql://USUARIO:SENHA@HOST/BANCO?sslmode=require "
               "(no Neon: Connect → Copy snippet).")
    convertido = converter_database_url(valor)
    if not convertido:
        dica = ""
        if "postgres" not in valor:
            dica = " Ela não começa com postgresql://."
        elif "@" not in valor:
            dica = " Falta o usuário e a senha (a parte antes do @)."
        return (f"A variável DATABASE_URL está preenchida ({len(valor.strip())} caracteres), mas não é uma "
                f"connection string do PostgreSQL.{dica} {formato}")
    if "***" in convertido.get("DB_PASSWORD", ""):
        return ("A senha na DATABASE_URL está escondida com asteriscos (foi copiada do texto da tela). "
                "Copie a connection string pelo botão de copiar do Neon, que traz a senha de verdade.")
    return None


def _decodificar(valor: str) -> str:
    return unquote(valor)


def montar_url_sqlalchemy(db_url: str, usuario: str | None, senha: str | None) -> str:
    url = db_url.strip()
    if url.startswith("jdbc:"):
        url = url[len("jdbc:"):]
    for prefixo in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefixo):
            resto = url[len(prefixo):]
            break
    else:
        raise ValueError("DB_URL deve começar com postgresql:// (ou jdbc:postgresql://)")
    if "@" in resto.split("/", 1)[0]:
        credenciais_url, resto = resto.split("@", 1)
        if not usuario:
            partes = credenciais_url.split(":", 1)
            usuario = unquote(partes[0])
            senha = senha or (unquote(partes[1]) if len(partes) == 2 else None)
    credenciais = ""
    if usuario:
        credenciais = quote(usuario, safe="")
        if senha:
            credenciais += ":" + quote(senha, safe="")
        credenciais += "@"
    return f"postgresql+psycopg://{credenciais}{resto}"


def _duracao_segundos(texto: str, padrao: float) -> float:
    if not texto:
        return padrao
    t = texto.strip().lower()
    for sufixo, fator in (("ms", 0.001), ("s", 1.0), ("m", 60.0), ("h", 3600.0)):
        if t.endswith(sufixo):
            return float(t[: -len(sufixo)]) * fator
    return float(t)


def _booleano(texto: str | None, padrao: bool = False) -> bool:
    if texto is None or texto.strip() == "":
        return padrao
    return texto.strip().lower() in ("true", "1", "sim", "yes", "on")


@dataclass(frozen=True)
class Integracoes:
    timeout_conexao: float = 5.0
    timeout_leitura: float = 25.0
    viacep_url: str = "https://viacep.com.br/ws"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_intervalo_minimo: float = 1.1
    photon_url: str = "https://photon.komoot.io"
    photon_intervalo_minimo: float = 1.1
    ibge_url: str = "https://servicodados.ibge.gov.br/api/v1/localidades"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    elevacao_url: str = "https://api.open-meteo.com/v1/elevation"
    previsao_url: str = "https://api.open-meteo.com/v1/forecast"
    vazao_url: str = "https://flood-api.open-meteo.com/v1/flood"
    sgb_setores_risco_url: str = (
        "https://geoportal.sgb.gov.br/server/rest/services/gestaoterritorial/risco/MapServer/0")
    rotas_url: str = "https://valhalla1.openstreetmap.de"
    rotas_chave_api: str = ""
    rotas_intervalo_minimo: float = 1.1


@dataclass(frozen=True)
class Analise:
    raio_cursos_agua_metros: int = 1500
    raio_ocorrencias_metros: int = 500
    raio_setores_risco_metros: int = 300
    anos_historico: int = 30


@dataclass(frozen=True)
class Limites:
    consultas_por_minuto: int = 15
    relatos_por_hora: int = 10
    autenticacao_por_minuto: int = 10
    rotas_por_minuto: int = 10


@dataclass(frozen=True)
class Admin:
    nome: str = "Administrador"
    email: str = ""
    senha: str = ""


@dataclass(frozen=True)
class Configuracoes:
    porta: int = 8080
    db_url: str = PADRAO_DB_URL
    db_usuario: str = "alertalar"
    db_senha: str = ""
    db_pool: int = 10
    origem_banco: str = "nenhuma variável (DATABASE_URL e DB_URL vazias)"
    cookie_seguro: bool = False
    confiar_proxy: bool = False
    contato_email: str = ""
    nome_aplicacao: str = "AlertaLar/1.0"
    url_publica: str = ""
    admin: Admin = field(default_factory=Admin)
    cors_origens: tuple[str, ...] = ()
    pasta_frontend: Path | None = None
    integracoes: Integracoes = field(default_factory=Integracoes)
    analise: Analise = field(default_factory=Analise)
    limites: Limites = field(default_factory=Limites)
    aplicar_migracoes: bool = True

    @property
    def user_agent(self) -> str:
        partes = []
        if self.url_publica.strip():
            partes.append("+" + self.url_publica.strip())
        if self.contato_email.strip():
            partes.append(self.contato_email.strip())
        return self.nome_aplicacao if not partes else f"{self.nome_aplicacao} ({'; '.join(partes)})"

    @property
    def url_banco(self) -> str:
        return montar_url_sqlalchemy(self.db_url, self.db_usuario, self.db_senha)

    @property
    def descricao_banco(self) -> str:
        url = self.db_url[len("jdbc:"):] if self.db_url.startswith("jdbc:") else self.db_url
        try:
            partes = urlsplit(url)
            porta = f":{partes.port}" if partes.port else ""
            return f"{partes.hostname}{porta}{partes.path or ''}"
        except ValueError:
            return "(endereço inválido)"

    @classmethod
    def do_ambiente(cls, env: dict[str, str] | None = None) -> Configuracoes:
        e = ler_env() if env is None else env
        banco: dict[str, str] = {}
        origem = "nenhuma variável (DATABASE_URL e DB_URL vazias)"
        if e.get("DATABASE_URL", "").strip():
            if not e.get("DB_URL"):
                problema = problema_database_url(e["DATABASE_URL"])
                if problema:
                    raise ConfiguracaoInvalida(problema)
            banco = converter_database_url(e["DATABASE_URL"])
            origem = "DATABASE_URL"
        for chave in ("DB_URL", "DB_USERNAME", "DB_PASSWORD"):
            if e.get(chave):
                banco[chave] = e[chave]
        if e.get("DB_URL"):
            origem = "DB_URL"
        g = e.get
        integ = Integracoes(
            viacep_url=g("VIACEP_URL") or Integracoes.viacep_url,
            nominatim_url=g("NOMINATIM_URL") or Integracoes.nominatim_url,
            photon_url=g("PHOTON_URL") or Integracoes.photon_url,
            ibge_url=g("IBGE_URL") or Integracoes.ibge_url,
            overpass_url=g("OVERPASS_URL") or Integracoes.overpass_url,
            elevacao_url=g("OPEN_METEO_ELEVACAO_URL") or Integracoes.elevacao_url,
            previsao_url=g("OPEN_METEO_PREVISAO_URL") or Integracoes.previsao_url,
            vazao_url=g("OPEN_METEO_VAZAO_URL") or Integracoes.vazao_url,
            sgb_setores_risco_url=g("SGB_SETORES_RISCO_URL") or Integracoes.sgb_setores_risco_url,
            rotas_url=g("ROTAS_URL") or Integracoes.rotas_url,
            rotas_chave_api=g("ROTAS_CHAVE_API") or "",
            timeout_conexao=_duracao_segundos(g("ALERTALAR_TIMEOUT_CONEXAO", ""), 5.0),
            timeout_leitura=_duracao_segundos(g("ALERTALAR_TIMEOUT_LEITURA", ""), 25.0),
        )
        frontend = g("ALERTALAR_FRONTEND")
        return cls(
            porta=int(g("PORT") or 8080),
            db_url=banco.get("DB_URL", PADRAO_DB_URL),
            db_usuario=banco.get("DB_USERNAME", "alertalar"),
            db_senha=banco.get("DB_PASSWORD", ""),
            db_pool=int(g("DB_POOL") or 10),
            origem_banco=origem,
            cookie_seguro=_booleano(g("COOKIE_SECURE")),
            confiar_proxy=(g("FORWARD_HEADERS_STRATEGY") or "none").strip().lower() in ("framework", "native"),
            contato_email=g("ALERTALAR_CONTATO_EMAIL") or "",
            url_publica=g("ALERTALAR_URL_PUBLICA") or g("RENDER_EXTERNAL_URL") or "",
            admin=Admin(nome=g("ALERTALAR_ADMIN_NOME") or "Administrador",
                        email=g("ALERTALAR_ADMIN_EMAIL") or "",
                        senha=g("ALERTALAR_ADMIN_SENHA") or ""),
            cors_origens=tuple(o.strip() for o in (g("ALERTALAR_CORS_ORIGENS") or "").split(",") if o.strip()),
            pasta_frontend=Path(frontend) if frontend else None,
            integracoes=integ,
            aplicar_migracoes=_booleano(g("ALERTALAR_APLICAR_MIGRACOES"), True),
        )
