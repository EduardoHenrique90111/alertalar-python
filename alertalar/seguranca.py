"""Segurança da aplicação:

- sessão com cookie HttpOnly + proteção CSRF (token no cookie XSRF-TOKEN, enviado no cabeçalho
  X-XSRF-TOKEN pelo front-end);
- rotas /api/admin/** restritas ao papel ADMIN e /api/consultas/minhas a quem entrou;
- cabeçalhos: Content-Security-Policy, X-Frame-Options, Referrer-Policy, Permissions-Policy;
- limite de requisições por IP nas rotas sensíveis;
- CORS: por padrão só a própria origem (origens extras em ALERTALAR_CORS_ORIGENS).

Tudo isso fica num middleware ASGI único, que roda antes das rotas da API e dos arquivos do site.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from http.cookies import SimpleCookie

from alertalar.config import Configuracoes, Limites
from alertalar.erros import TIPO_PROBLEMA, corpo_erro_inesperado

COOKIE_SESSAO = "ALERTALAR_SESSAO"
COOKIE_CSRF = "XSRF-TOKEN"
CABECALHO_CSRF = "X-XSRF-TOKEN"
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CHAVE_ESCOPO = "alertalar.seguranca"

# Somente recursos próprios + blocos do mapa do OpenStreetMap. Sem scripts ou estilos inline.
CSP = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org",
    "connect-src 'self'",
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))


# ---------------------------------------------------------------- sessões

@dataclass
class Sessao:
    id: str
    email: str | None = None
    papel: str | None = None
    ultimo_acesso: float = field(default_factory=time.monotonic)


class ArmazemSessoes:
    """Sessões em memória (como as da versão em Java). Expiram após 60 minutos sem uso; reiniciar
    o servidor encerra todas."""

    def __init__(self, duracao_segundos: float = 3600, relogio: Callable[[], float] = time.monotonic):
        self.duracao = duracao_segundos
        self._relogio = relogio
        self._sessoes: dict[str, Sessao] = {}
        self._trava = threading.Lock()
        self._ultima_limpeza = relogio()

    def obter(self, id_sessao: str | None) -> Sessao | None:
        if not id_sessao:
            return None
        agora = self._relogio()
        with self._trava:
            self._limpar_se_preciso(agora)
            sessao = self._sessoes.get(id_sessao)
            if sessao is None:
                return None
            if agora - sessao.ultimo_acesso > self.duracao:
                del self._sessoes[id_sessao]
                return None
            sessao.ultimo_acesso = agora
            return sessao

    def criar(self, email: str, papel: str) -> Sessao:
        sessao = Sessao(secrets.token_urlsafe(32), email, papel, self._relogio())
        with self._trava:
            self._sessoes[sessao.id] = sessao
        return sessao

    def remover(self, id_sessao: str | None) -> None:
        if id_sessao:
            with self._trava:
                self._sessoes.pop(id_sessao, None)

    def _limpar_se_preciso(self, agora: float) -> None:
        if agora - self._ultima_limpeza < 60:
            return
        self._ultima_limpeza = agora
        for chave in [k for k, s in self._sessoes.items() if agora - s.ultimo_acesso > self.duracao]:
            del self._sessoes[chave]


class ContextoSeguranca:
    """Situação de segurança da requisição atual, guardada no escopo ASGI para as rotas."""

    def __init__(self, armazem: ArmazemSessoes, sessao: Sessao | None, token_csrf: str | None):
        self._armazem = armazem
        self.sessao = sessao
        self.token_csrf = token_csrf
        self.cookie_sessao: str | None = None  # novo valor do cookie ("" apaga)
        self.cookie_csrf: str | None = None

    @property
    def email(self) -> str | None:
        return None if self.sessao is None else self.sessao.email

    @property
    def papel(self) -> str | None:
        return None if self.sessao is None else self.sessao.papel

    def autenticar(self, email: str, papel: str) -> None:
        """Proteção contra fixação de sessão: novo identificador e novo token CSRF após entrar."""
        if self.sessao is not None:
            self._armazem.remover(self.sessao.id)
        self.sessao = self._armazem.criar(email, papel)
        self.cookie_sessao = self.sessao.id
        self.cookie_csrf = novo_token()

    def encerrar(self) -> None:
        if self.sessao is not None:
            self._armazem.remover(self.sessao.id)
        self.sessao = None
        self.cookie_sessao = ""
        self.cookie_csrf = ""


def novo_token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------- limite de requisições

class LimitadorRequisicoes:
    """Limite de requisições por chave (ex.: IP + rota) em janela deslizante, em memória.
    Para várias instâncias do servidor, troque por um limitador distribuído (ex.: Redis)."""

    MAXIMO_CHAVES = 50_000

    def __init__(self, relogio: Callable[[], float] = time.time):
        self._relogio = relogio
        self._janelas: dict[str, deque[float]] = {}
        self._trava = threading.Lock()

    def permitir(self, chave: str, limite: int, janela_segundos: float) -> bool:
        """True se a requisição pode prosseguir."""
        agora = self._relogio()
        inicio = agora - janela_segundos
        with self._trava:
            if len(self._janelas) > self.MAXIMO_CHAVES:
                for k in [k for k, f in self._janelas.items() if not f or f[-1] < inicio]:
                    del self._janelas[k]
            fila = self._janelas.setdefault(chave, deque())
            while fila and fila[0] < inicio:
                fila.popleft()
            if len(fila) >= limite:
                return False
            fila.append(agora)
            return True


@dataclass(frozen=True)
class Regra:
    grupo: str
    limite: int
    janela_segundos: int


def regra_para(metodo: str, caminho: str, limites: Limites) -> Regra | None:
    """Rotas que consomem APIs externas ou recebem formulários têm limite por IP."""
    if not caminho.startswith("/api/"):
        return None
    post = metodo == "POST"
    if post and caminho == "/api/consultas":
        return Regra("consulta", limites.consultas_por_minuto, 60)
    if caminho.startswith("/api/enderecos/"):
        return Regra("endereco", limites.consultas_por_minuto * 2, 60)
    if post and caminho == "/api/ocorrencias":
        return Regra("relato", limites.relatos_por_hora, 3600)
    if post and caminho in ("/api/auth/login", "/api/auth/registro"):
        return Regra("auth", limites.autenticacao_por_minuto, 60)
    if caminho.startswith("/api/rotas/"):
        return Regra("rota", limites.rotas_por_minuto, 60)
    if caminho.startswith("/api/situacao-atual"):
        return Regra("situacao", 30, 60)
    return None


# ---------------------------------------------------------------- middleware

def _problema(status: int, titulo: str, detalhe: str) -> bytes:
    return json.dumps({"type": "about:blank", "title": titulo, "status": status, "detail": detalhe},
                      ensure_ascii=False).encode("utf-8")


def _cookie(nome: str, valor: str, seguro: bool, http_only: bool) -> bytes:
    partes = [f"{nome}={valor}", "Path=/", "SameSite=Lax"]
    if valor == "":
        partes.append("Max-Age=0")
    if http_only:
        partes.append("HttpOnly")
    if seguro:
        partes.append("Secure")
    return "; ".join(partes).encode("latin-1")


class MiddlewareSeguranca:
    def __init__(self, app, config: Configuracoes, armazem: ArmazemSessoes | None = None,
                 limitador: LimitadorRequisicoes | None = None):
        self.app = app
        self.config = config
        self.armazem = armazem or ArmazemSessoes()
        self.limitador = limitador or LimitadorRequisicoes()
        self.origens = frozenset(o.rstrip("/") for o in config.cors_origens)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        metodo = scope["method"]
        caminho = scope["path"]
        cabecalhos = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        cookies = SimpleCookie()
        try:
            cookies.load(cabecalhos.get("cookie", ""))
        except Exception:  # noqa: BLE001 - cookie malformado é ignorado
            pass
        https = scope.get("scheme") == "https"
        seguro = self.config.cookie_seguro or https
        extras: list[tuple[bytes, bytes]] = []

        async def responder(status: int, corpo: bytes = b"", tipo: str | None = TIPO_PROBLEMA,
                            adicionais: list[tuple[bytes, bytes]] | None = None) -> None:
            headers = [] if not corpo else [(b"content-type", tipo.encode()), (b"content-length", str(len(corpo)).encode())]
            headers += (adicionais or []) + extras
            headers += self._cabecalhos_seguranca(https)
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": corpo})

        # CORS: só a própria origem, além das liberadas na configuração
        origem = cabecalhos.get("origin")
        if caminho.startswith("/api/") and origem and not self._mesma_origem(origem, cabecalhos):
            if origem.rstrip("/") not in self.origens:
                await responder(403, _problema(403, "Acesso negado", "Origem não autorizada."))
                return
            extras += [(b"access-control-allow-origin", origem.encode("latin-1")),
                       (b"access-control-allow-credentials", b"true"), (b"vary", b"Origin")]
            if metodo == "OPTIONS" and "access-control-request-method" in cabecalhos:
                await responder(200, adicionais=[(b"access-control-allow-methods", b"GET,POST,PATCH,OPTIONS"),
                                                 (b"access-control-allow-headers", b"Content-Type,X-XSRF-TOKEN"),
                                                 (b"access-control-max-age", b"3600")])
                return

        id_sessao = cookies[COOKIE_SESSAO].value if COOKIE_SESSAO in cookies else None
        sessao = self.armazem.obter(id_sessao)
        token = cookies[COOKIE_CSRF].value if COOKIE_CSRF in cookies else None
        contexto = ContextoSeguranca(self.armazem, sessao, token or None)
        if id_sessao and sessao is None:
            contexto.cookie_sessao = ""  # sessão expirada: apaga o cookie velho
        if not token:
            contexto.cookie_csrf = novo_token()
        scope[CHAVE_ESCOPO] = contexto

        def cookies_resposta() -> list[tuple[bytes, bytes]]:
            lista = []
            if contexto.cookie_sessao is not None:
                lista.append((b"set-cookie", _cookie(COOKIE_SESSAO, contexto.cookie_sessao, seguro, True)))
            if contexto.cookie_csrf is not None:
                lista.append((b"set-cookie", _cookie(COOKIE_CSRF, contexto.cookie_csrf, seguro, False)))
            return lista

        # CSRF: toda requisição que altera dados precisa repetir no cabeçalho o token do cookie
        if metodo not in METODOS_SEGUROS:
            enviado = cabecalhos.get(CABECALHO_CSRF.lower())
            if not token or not enviado or not hmac.compare_digest(token.encode(), enviado.encode()):
                await responder(403, _problema(
                    403, "Token de segurança inválido", "Sua sessão expirou ou o token de segurança está ausente. "
                    "Recarregue a página e tente novamente."), adicionais=cookies_resposta())
                return

        if metodo == "POST" and caminho == "/api/auth/logout":
            contexto.encerrar()
            await responder(204, adicionais=cookies_resposta())
            return

        regra = regra_para(metodo, caminho, self.config.limites)
        if regra is not None:
            ip = (scope.get("client") or ("desconhecido", 0))[0]
            if not self.limitador.permitir(f"{regra.grupo}|{ip}", regra.limite, regra.janela_segundos):
                await responder(429, _problema(
                    429, "Muitas requisições", "Você fez muitas solicitações em pouco tempo. Aguarde alguns "
                    "instantes e tente novamente."), adicionais=[(b"retry-after", str(regra.janela_segundos).encode())])
                return

        precisa_admin = caminho.startswith("/api/admin/") or caminho == "/api/admin"
        precisa_login = precisa_admin or (metodo == "GET" and caminho == "/api/consultas/minhas")
        if precisa_login and contexto.email is None:
            await responder(401, _problema(401, "Não autenticado", "Faça login para acessar este recurso."),
                            adicionais=cookies_resposta())
            return
        if precisa_admin and contexto.papel != "ADMIN":
            await responder(403, _problema(403, "Acesso negado", "Você não tem permissão para acessar este recurso."),
                            adicionais=cookies_resposta())
            return

        iniciada = False

        async def enviar(mensagem):
            nonlocal iniciada
            if mensagem["type"] == "http.response.start":
                iniciada = True
                existentes = {k.lower() for k, _ in mensagem.get("headers", [])}
                headers = list(mensagem.get("headers", [])) + extras + cookies_resposta()
                headers += [h for h in self._cabecalhos_seguranca(https) if h[0] not in existentes]
                mensagem = {**mensagem, "headers": headers}
            await send(mensagem)

        try:
            await self.app(scope, receive, enviar)
        except Exception as ex:  # noqa: BLE001 - erro não previsto vira 500 sem detalhes internos
            if iniciada:
                raise
            corpo = json.dumps(corpo_erro_inesperado(ex, caminho), ensure_ascii=False).encode("utf-8")
            await responder(500, corpo, adicionais=cookies_resposta())

    @staticmethod
    def _mesma_origem(origem: str, cabecalhos: dict[str, str]) -> bool:
        host = cabecalhos.get("x-forwarded-host") or cabecalhos.get("host") or ""
        sem_esquema = origem.split("://", 1)[-1].rstrip("/")
        return sem_esquema.lower() == host.lower()

    @staticmethod
    def _cabecalhos_seguranca(https: bool) -> list[tuple[bytes, bytes]]:
        lista = [
            (b"content-security-policy", CSP.encode()),
            (b"x-frame-options", b"DENY"),
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"permissions-policy", b"geolocation=(self), camera=(), microphone=(), payment=()"),
            (b"x-xss-protection", b"0"),
            (b"cache-control", b"no-cache, no-store, max-age=0, must-revalidate"),
            (b"pragma", b"no-cache"),
            (b"expires", b"0"),
        ]
        if https:
            lista.append((b"strict-transport-security", b"max-age=31536000 ; includeSubDomains"))
        return lista
