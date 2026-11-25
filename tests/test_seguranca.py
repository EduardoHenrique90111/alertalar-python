"""Limite de requisições, sessões, CSRF, hash de senhas e tratamento de erros sem vazamento de detalhes
internos."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from alertalar.config import Configuracoes, Limites
from alertalar.erros import (
    EnderecoNaoEncontrado,
    FalhaAutenticacao,
    IntegracaoExterna,
    PrecisaoInsuficiente,
    RegraNegocio,
    registrar_tratadores,
)
from alertalar.seguranca import (
    CHAVE_ESCOPO,
    ArmazemSessoes,
    LimitadorRequisicoes,
    MiddlewareSeguranca,
    regra_para,
)
from alertalar.servicos.usuarios import confere_senha, gerar_hash


class Relogio:
    def __init__(self, agora: float = 1_000_000.0):
        self.agora = agora

    def __call__(self) -> float:
        return self.agora


def test_limitador_bloqueia_apos_o_limite_e_libera_quando_a_janela_passa():
    relogio = Relogio()
    limitador = LimitadorRequisicoes(relogio)
    assert limitador.permitir("ip", 2, 60)
    assert limitador.permitir("ip", 2, 60)
    assert not limitador.permitir("ip", 2, 60)
    assert limitador.permitir("outro-ip", 2, 60)
    relogio.agora += 61
    assert limitador.permitir("ip", 2, 60)


def test_regras_de_limite_se_aplicam_as_rotas_sensiveis():
    limites = Limites(15, 10, 10, 10)
    assert regra_para("POST", "/api/consultas", limites).grupo == "consulta"
    assert regra_para("POST", "/api/ocorrencias", limites).grupo == "relato"
    assert regra_para("POST", "/api/auth/login", limites).grupo == "auth"
    assert regra_para("GET", "/api/rotas/segura", limites).grupo == "rota"
    assert regra_para("GET", "/api/enderecos/buscar", limites).limite == 30
    assert regra_para("GET", "/api/ocorrencias", limites) is None
    assert regra_para("GET", "/index.html", limites) is None


def test_senhas_sao_guardadas_com_bcrypt():
    h1 = gerar_hash("senhaSegura1", 4)
    h2 = gerar_hash("senhaSegura1", 4)
    assert h1 != h2
    assert h1.startswith("$2")
    assert confere_senha("senhaSegura1", h1)
    assert not confere_senha("outra", h1)
    # hash gerado pelo Spring Security da versão em Java (BCryptPasswordEncoder, custo 4): continua valendo
    hash_java = "$2a$04$ZdC5CwIWmREEn5IylswXKu5NnsuwOX9.DvwcA0b5LaXZzB/cnJPCi"
    assert confere_senha("senhaSegura1", hash_java)
    assert not confere_senha("senhaSegura2", hash_java)


def test_sessoes_expiram_sem_uso():
    relogio = Relogio()
    armazem = ArmazemSessoes(3600, relogio)
    sessao = armazem.criar("ana@exemplo.com", "USUARIO")
    assert armazem.obter(sessao.id) is sessao
    relogio.agora += 3599
    assert armazem.obter(sessao.id) is sessao, "o uso renova o prazo"
    relogio.agora += 3601
    assert armazem.obter(sessao.id) is None
    assert armazem.obter("inventada") is None


# ---------------------------------------------------------------- aplicação mínima

def _app(limites: Limites = Limites()) -> FastAPI:
    app = FastAPI()
    registrar_tratadores(app)

    @app.get("/api/erro/{tipo}")
    def erro(tipo: str):
        raise {
            "endereco": EnderecoNaoEncontrado("x"),
            "regra": RegraNegocio("x"),
            "integracao": IntegracaoExterna("ViaCEP", "fora do ar"),
            "login": FalhaAutenticacao(),
            "precisao": PrecisaoInsuficiente("aproximado", -29.9, -51.1),
            "interno": RuntimeError("SELECT * FROM usuario; senha=123"),
        }[tipo]

    @app.post("/api/entrar")
    def entrar(request: Request):
        request.scope[CHAVE_ESCOPO].autenticar("ana@exemplo.com", "ADMIN")
        return {"ok": True}

    @app.get("/api/admin/resumo")
    def resumo(request: Request):
        return {"email": request.scope[CHAVE_ESCOPO].email}

    @app.post("/api/auth/login")
    def login():
        return {"ok": True}

    app.add_middleware(MiddlewareSeguranca, config=Configuracoes(limites=limites))
    return app


@pytest.fixture
def cliente():
    with TestClient(_app(), raise_server_exceptions=False) as c:
        yield c


def _csrf(cliente) -> dict:
    cliente.get("/api/qualquer")
    return {"X-XSRF-TOKEN": cliente.cookies.get("XSRF-TOKEN")}


def test_erros_de_negocio_viram_respostas_http_adequadas(cliente):
    assert cliente.get("/api/erro/endereco").status_code == 404
    assert cliente.get("/api/erro/regra").status_code == 422
    integracao = cliente.get("/api/erro/integracao")
    assert integracao.status_code == 503
    assert integracao.json()["fonte"] == "ViaCEP"
    login = cliente.get("/api/erro/login")
    assert login.status_code == 401
    assert login.json()["detail"] == "E-mail ou senha incorretos."  # não informa se o e-mail existe
    precisao = cliente.get("/api/erro/precisao")
    assert precisao.status_code == 422
    assert precisao.json()["codigo"] == "PRECISAO_INSUFICIENTE"
    assert precisao.headers["content-type"] == "application/problem+json"


def test_erro_inesperado_nao_expoe_a_mensagem_interna(cliente):
    r = cliente.get("/api/erro/interno")
    assert r.status_code == 500
    assert "SELECT" not in r.text
    assert "Código para suporte" in r.json()["detail"]
    assert r.headers["x-frame-options"] == "DENY", "cabeçalhos de segurança também no erro"


def test_csrf_obrigatorio_e_sessao_nova_ao_entrar(cliente):
    assert cliente.post("/api/entrar").status_code == 403
    assert cliente.post("/api/entrar", headers={"X-XSRF-TOKEN": "inventado"}).status_code == 403
    cabecalho = _csrf(cliente)
    token_antes = cabecalho["X-XSRF-TOKEN"]
    r = cliente.post("/api/entrar", headers=cabecalho)
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    sessao = next(c for c in cookies if c.startswith("ALERTALAR_SESSAO="))
    assert "HttpOnly" in sessao and "SameSite=Lax" in sessao
    assert cliente.cookies.get("XSRF-TOKEN") != token_antes
    assert cliente.get("/api/admin/resumo").json() == {"email": "ana@exemplo.com"}

    # sair encerra a sessão no servidor (o cookie antigo deixa de valer)
    id_antigo = cliente.cookies.get("ALERTALAR_SESSAO")
    assert cliente.post("/api/auth/logout", headers={"X-XSRF-TOKEN": cliente.cookies.get("XSRF-TOKEN")}).status_code == 204
    cliente.cookies.set("ALERTALAR_SESSAO", id_antigo)
    assert cliente.get("/api/admin/resumo").status_code == 401


def test_limite_de_tentativas_de_login_responde_429_com_retry_after():
    with TestClient(_app(Limites(autenticacao_por_minuto=2))) as c:
        cabecalho = _csrf(c)
        assert c.post("/api/auth/login", headers=cabecalho).status_code == 200
        assert c.post("/api/auth/login", headers=cabecalho).status_code == 200
        r = c.post("/api/auth/login", headers=cabecalho)
        assert r.status_code == 429
        assert r.headers["retry-after"] == "60"
        assert r.json()["title"] == "Muitas requisições"


def test_cors_so_libera_a_propria_origem_e_as_configuradas():
    app = FastAPI()
    app.add_middleware(MiddlewareSeguranca, config=Configuracoes(cors_origens=("https://parceiro.org",)))

    @app.get("/api/x")
    def x():
        return {}

    with TestClient(app) as c:
        assert c.get("/api/x", headers={"Origin": "http://testserver"}).status_code == 200
        assert c.get("/api/x", headers={"Origin": "https://outro.com"}).status_code == 403
        liberada = c.get("/api/x", headers={"Origin": "https://parceiro.org"})
        assert liberada.headers["access-control-allow-origin"] == "https://parceiro.org"
        pre = c.options("/api/x", headers={"Origin": "https://parceiro.org", "Access-Control-Request-Method": "POST"})
        assert pre.status_code == 200
        assert "X-XSRF-TOKEN" in pre.headers["access-control-allow-headers"]
