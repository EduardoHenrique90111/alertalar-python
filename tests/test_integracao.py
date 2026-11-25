"""Teste de ponta a ponta: sobe a aplicação inteira (FastAPI + Uvicorn + PostgreSQL real), com as APIs
externas simuladas por um servidor HTTP local, e percorre os fluxos principais: consulta de risco,
gravação, relato, moderação, importação oficial, situação atual, cadastro/login, rota segura e
proteções de segurança.

Executado somente quando ALERTALAR_TEST_DB_URL aponta para um banco PostgreSQL EXCLUSIVO PARA TESTES
(os dados dele são apagados). Veja o README.
"""

from __future__ import annotations

import json
import re
import threading
import time
from urllib.parse import quote

import pytest
import requests
import uvicorn
from sqlalchemy import create_engine, text

from alertalar import container
from alertalar.aplicacao import criar_app
from alertalar.config import Admin, Configuracoes, Integracoes, Limites
from tests.apoio import respostas as rs
from tests.apoio.banco import precisa_banco, url_banco_teste
from tests.apoio.servidor_falso import Resposta, ServidorHttpFalso

pytestmark = precisa_banco

ADMIN_EMAIL = "admin.teste@alertalar.local"
ADMIN_SENHA = "SenhaAdmin2026"


class Estado:
    """Respostas que os testes trocam durante a execução."""

    sgb = rs.sgb_sem_setores()
    nominatim = rs.nominatim_numero()
    status_nominatim = 200  # 429 simula o limite de pedidos do Nominatim público


def _rotas_falsas(apis: ServidorHttpFalso) -> None:
    def nominatim(req):
        if Estado.status_nominatim == 200:
            return Resposta.json(Estado.nominatim)
        return Resposta(Estado.status_nominatim, "<html><body>Too Many Requests</body></html>")

    def valhalla(req):
        locais = json.loads(req.corpo)["locations"]
        return Resposta.json(rs.valhalla_rota(locais[0]["lat"], locais[0]["lon"], locais[1]["lat"], locais[1]["lon"]))

    from datetime import datetime, timezone
    apis.rota("/viacep/", Resposta.json(rs.via_cep())) \
        .rota("/nominatim/search", nominatim) \
        .rota("/photon/api", lambda r: Resposta.json(rs.photon(re.sub(r"\D+", "", r.parametro("q"))))) \
        .rota("/ibge/estados/RS/municipios", Resposta.json(rs.ibge_municipios_rs())) \
        .rota("/overpass", Resposta.json(rs.overpass_com_rio_e_corrego())) \
        .rota("/elevacao", lambda r: Resposta.json(rs.elevacao(len(r.parametro("latitude").split(","))))) \
        .rota("/previsao", lambda r: Resposta.json(rs.previsao_chuva(datetime.now(timezone.utc)))) \
        .rota("/vazao", lambda r: Resposta.json(rs.vazao(datetime.now(timezone.utc).date()))) \
        .rota("/sgb/query", lambda r: Resposta.json(Estado.sgb)) \
        .rota("/valhalla/route", valhalla)


@pytest.fixture(scope="module")
def ambiente():
    url = url_banco_teste()
    engine = create_engine(url)
    with engine.begin() as cx:
        existe = cx.execute(text("SELECT to_regclass('consulta') IS NOT NULL")).scalar()
        if existe:
            cx.execute(text("TRUNCATE consulta_fator, consulta, ocorrencia, endereco, usuario RESTART IDENTITY CASCADE"))

    apis = ServidorHttpFalso()
    _rotas_falsas(apis)
    integ = Integracoes(
        viacep_url=apis.url("/viacep"), nominatim_url=apis.url("/nominatim"), nominatim_intervalo_minimo=0.01,
        photon_url=apis.url("/photon"), photon_intervalo_minimo=0.01, ibge_url=apis.url("/ibge"),
        overpass_url=apis.url("/overpass"), elevacao_url=apis.url("/elevacao"), previsao_url=apis.url("/previsao"),
        vazao_url=apis.url("/vazao"), sgb_setores_risco_url=apis.url("/sgb"), rotas_url=apis.url("/valhalla"),
        rotas_intervalo_minimo=0.01, timeout_leitura=5.0)
    config = Configuracoes(db_url=url, db_usuario="", db_senha="", db_pool=5,
                           admin=Admin(email=ADMIN_EMAIL, senha=ADMIN_SENHA), integracoes=integ,
                           limites=Limites(rotas_por_minuto=30))
    servicos = container.montar(config, custo_bcrypt=4)
    app = criar_app(config, servicos)
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    limite = time.monotonic() + 120
    while not servidor.started:
        assert time.monotonic() < limite, "a aplicação não subiu"
        time.sleep(0.05)
    porta = servidor.servers[0].sockets[0].getsockname()[1]

    with engine.begin() as cx:
        historico_oficial = cx.execute(text("SELECT count(*) FROM historico_migracoes WHERE versao = 4")).scalar() == 1
        # A migração V4 carrega a base oficial do Atlas (27 mil registros) num banco novo; os testes abaixo
        # partem de um banco sem ocorrências para conferir contagens exatas (o administrador é mantido).
        cx.execute(text("TRUNCATE consulta_fator, consulta, ocorrencia RESTART IDENTITY CASCADE"))

    yield {"base": f"http://127.0.0.1:{porta}", "apis": apis, "historico_oficial": historico_oficial}

    servidor.should_exit = True
    thread.join(10)
    servicos.encerrar()
    apis.fechar()
    engine.dispose()


class Cliente:
    """Navegador mínimo: guarda cookies de sessão e envia o token CSRF como o front-end faz."""

    def __init__(self, base: str):
        self.base = base
        self.http = requests.Session()

    def get_json(self, caminho: str):
        r = self.enviar("GET", caminho)
        assert r.status_code == 200, f"{caminho} → {r.text}"
        return r.json()

    def login(self, email: str, senha: str) -> None:
        r = self.enviar("POST", "/api/auth/login", {"email": email, "senha": senha}, csrf=True)
        assert r.status_code == 200, r.text

    def enviar(self, metodo: str, caminho: str, corpo=None, csrf: bool = False, **extras) -> requests.Response:
        cabecalhos = {"Accept": "application/json"}
        if csrf:
            cabecalhos["X-XSRF-TOKEN"] = self.token()
        return self.http.request(metodo, self.base + caminho, json=corpo, headers=cabecalhos, timeout=60, **extras)

    def multipart(self, caminho: str, nome_arquivo: str, conteudo: str) -> requests.Response:
        return self.http.post(self.base + caminho, files={"arquivo": (nome_arquivo, conteudo.encode(), "text/csv")},
                              headers={"X-XSRF-TOKEN": self.token()}, timeout=60)

    def token(self) -> str:
        if self.http.cookies.get("XSRF-TOKEN") is None:
            self.enviar("GET", "/api/auth/csrf")
        t = self.http.cookies.get("XSRF-TOKEN")
        assert t, "cookie XSRF-TOKEN não recebido"
        return t


def fator(consulta: dict, codigo: str) -> dict:
    return next(f for f in consulta["fatores"] if f["codigo"] == codigo)


def ler_eventos(corpo: str) -> list[tuple[str, str]]:
    """Eventos de um corpo text/event-stream: (nome, dados)."""
    eventos = []
    for bloco in re.split(r"\r?\n\r?\n", corpo):
        nome, dados = "message", []
        for linha in re.split(r"\r?\n", bloco):
            if linha.startswith("event:"):
                nome = linha[6:].strip()
            elif linha.startswith("data:"):
                dados.append(re.sub(r"^ ", "", linha[5:]))
        if dados:
            eventos.append((nome, "\n".join(dados)))
    return eventos


def corpo_consulta(com_coordenadas: bool = True, numero: str = "100") -> dict:
    corpo = {"rua": "Rua de Teste", "numero": numero, "cidade": "Canoas", "estado": "RS"}
    if com_coordenadas:
        corpo.update(latitude=rs.LAT, longitude=rs.LON)
    return corpo


# ------------------------------------------------------------------ testes (na ordem)

def test_01_fontes_de_dados_cadastradas_pela_migracao(ambiente):
    fontes = Cliente(ambiente["base"]).get_json("/api/fontes")
    assert len(fontes) >= 13
    assert "SGB_SETORES_RISCO" in json.dumps(fontes)


def test_02_seguranca_csrf_area_administrativa_e_cabecalhos(ambiente):
    c = Cliente(ambiente["base"])
    sem_csrf = c.enviar("POST", "/api/consultas", {})
    assert sem_csrf.status_code == 403
    assert sem_csrf.json()["title"] == "Token de segurança inválido"
    assert c.enviar("GET", "/api/admin/resumo").status_code == 401
    pagina = c.enviar("GET", "/index.html")
    assert "default-src 'self'" in pagina.headers.get("Content-Security-Policy", "")
    assert pagina.headers.get("X-Frame-Options") == "DENY"
    assert pagina.headers.get("X-Content-Type-Options") == "nosniff"
    assert "<html" in pagina.text.lower()


def test_03_validacao_de_entrada_devolve_400_com_erros_por_campo(ambiente):
    r = Cliente(ambiente["base"]).enviar("POST", "/api/consultas", {"rua": "", "cidade": "Canoas", "estado": "ZZ"},
                                         csrf=True)
    assert r.status_code == 400
    assert r.headers["Content-Type"].startswith("application/problem+json")
    erros = r.json()["erros"]
    assert "rua" in erros and "estado" in erros


def test_04_consulta_completa_geocodifica_analisa_grava_e_reabre_pelo_id(ambiente):
    Estado.sgb = rs.sgb_setor_contendo_ponto()
    c = Cliente(ambiente["base"])
    r = c.enviar("POST", "/api/consultas", {"cep": "92010-000", "rua": "Rua de Teste", "numero": "100",
                                            "cidade": "Canoas", "estado": "RS"}, csrf=True)
    assert r.status_code == 201, r.text
    consulta = r.json()
    assert r.headers["Location"] == f"/api/consultas/{consulta['id']}"
    assert consulta["classificacao"] == "ALTO"
    assert consulta["endereco"]["precisao"] == "NUMERO"
    assert consulta["endereco"]["codigoIbge"] == "4304606"
    assert len(consulta["fatores"]) == 5
    assert len(consulta["mapa"]["setoresRisco"]) == 1
    assert len(consulta["dimensoes"]) == 3

    reaberta = c.get_json(f"/api/consultas/{consulta['id']}")
    assert reaberta["classificacao"] == "ALTO"
    assert "SGB" in reaberta["justificativa"]
    assert "SGB_SETORES_RISCO" in json.dumps(reaberta["fontes"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z", reaberta["dataConsulta"])
    Estado.sgb = rs.sgb_sem_setores()


def test_05_endereco_localizado_so_no_nivel_de_cidade_nao_e_analisado(ambiente):
    Estado.nominatim = rs.nominatim_apenas_cidade()
    try:
        r = Cliente(ambiente["base"]).enviar("POST", "/api/consultas", {"rua": "Rua Desconhecida", "numero": "5",
                                                                        "cidade": "Canoas", "estado": "RS"}, csrf=True)
        assert r.status_code == 422
        assert r.json()["codigo"] == "PRECISAO_INSUFICIENTE"
        assert r.json()["latitudeAproximada"] == pytest.approx(-29.9128)
    finally:
        Estado.nominatim = rs.nominatim_numero()


def test_06_relato_fica_pendente_e_confirmado_pela_moderacao_passa_a_contar(ambiente):
    base = ambiente["base"]
    anonimo = Cliente(base)
    relato = {"localizacao": "Rua de Teste, 120", "municipio": "Canoas", "estado": "RS",
              "dataOcorrencia": "2024-05-04", "descricao": "A água cobriu a calçada e entrou na garagem.",
              "tipoEvento": "ALAGAMENTO", "latitude": rs.LAT + 0.0005, "longitude": rs.LON,
              "nomeRelator": "Morador", "contatoRelator": "morador@exemplo.com", "declaracaoVeracidade": True}
    criado = anonimo.enviar("POST", "/api/ocorrencias", relato, csrf=True)
    assert criado.status_code == 201, criado.text
    assert "morador@exemplo.com" not in criado.text, "contato do relator não pode ser exposto"
    assert anonimo.get_json("/api/ocorrencias")["total"] == 0, "relato pendente não é público"

    admin = Cliente(base)
    admin.login(ADMIN_EMAIL, ADMIN_SENHA)
    assert admin.get_json("/api/admin/resumo") == {"relatosPendentes": 1}
    pendentes = admin.get_json("/api/admin/ocorrencias?status=PENDENTE")
    assert pendentes["total"] == 1
    assert pendentes["itens"][0]["contatoRelator"] == "morador@exemplo.com"
    id_relato = pendentes["itens"][0]["ocorrencia"]["id"]
    validado = admin.enviar("PATCH", f"/api/admin/ocorrencias/{id_relato}/validacao",
                            {"status": "CONFIRMADA", "observacao": "Conferido"}, csrf=True)
    assert validado.status_code == 200, validado.text
    assert validado.json()["statusValidacao"] == "CONFIRMADA"

    assert anonimo.get_json("/api/ocorrencias")["total"] == 1
    proximas = anonimo.get_json(f"/api/ocorrencias/proximas?lat={rs.LAT}&lon={rs.LON}&raio=500")
    assert len(proximas) == 1
    assert proximas[0]["distanciaMetros"] == pytest.approx(56, abs=1)

    consulta = anonimo.enviar("POST", "/api/consultas", corpo_consulta(), csrf=True)
    assert consulta.status_code == 201, consulta.text
    f = fator(consulta.json(), "OCORRENCIAS_LOCAIS")
    assert f["situacao"] == "AVALIADO"
    assert f["pontuacao"] == 1


def test_07_importacao_da_planilha_oficial_alimenta_o_historico_municipal(ambiente):
    admin = Cliente(ambiente["base"])
    admin.login(ADMIN_EMAIL, ADMIN_SENHA)
    csv = ("Protocolo;UF;Município;Data do Evento;COBRADE\nTESTE-1;RS;Canoas;01/05/2024;1.2.1.0.0\n"
           "TESTE-2;RS;Canoas;15/06/2023;1.2.3.0.0\n")
    r = admin.multipart("/api/admin/importacoes/registros-oficiais", "registros.csv", csv)
    assert r.status_code == 200, r.text
    assert r.json()["importados"] == 2
    assert r.json()["estados"] == ["RS"]
    repetido = admin.multipart("/api/admin/importacoes/registros-oficiais", "registros.csv", csv)
    assert repetido.json()["duplicados"] == 2
    assert admin.multipart("/api/admin/importacoes/registros-oficiais", "planilha.xlsx", csv).status_code == 400

    consulta = Cliente(ambiente["base"]).enviar("POST", "/api/consultas", corpo_consulta(), csrf=True).json()
    assert fator(consulta, "HISTORICO_MUNICIPAL")["situacao"] == "AVALIADO"
    assert consulta["historicoMunicipal"]["total"] == 2


def test_08_situacao_atual_traz_chuva_e_vazao_separadas_da_classificacao(ambiente):
    s = Cliente(ambiente["base"]).get_json(f"/api/situacao-atual?lat={rs.LAT}&lon={rs.LON}")
    assert s["chuva"]["disponivel"]
    assert s["chuva"]["ultimas24hMm"] > 0
    assert s["vazao"]["tendencia"] == "SUBINDO"
    assert "40199" in json.dumps(s["avisos"])
    # 2 mm/h nas últimas horas simuladas = 48 mm em 24 h: perigo potencial (nível 1)
    assert s["riscoAgora"]["nivelChuva"] == 1, s
    assert s["riscoAgora"]["nivel"] == "ATENCAO", "sem consulta: suscetibilidade moderada"
    assert "INMET" in s["riscoAgora"]["criterio"]


def test_09_cadastro_login_automatico_e_historico_de_consultas(ambiente):
    c = Cliente(ambiente["base"])
    token_antes = c.token()
    reg = c.enviar("POST", "/api/auth/registro", {"nome": "Ana Teste", "email": "ana.teste@exemplo.com",
                                                  "senha": "senha1234"}, csrf=True)
    assert reg.status_code == 201, reg.text
    assert "senha" not in reg.text, "a senha/hash nunca deve voltar na resposta"
    assert c.http.cookies.get("XSRF-TOKEN") != token_antes, "token CSRF novo depois de entrar"
    assert c.get_json("/api/auth/me")["email"] == "ana.teste@exemplo.com"
    c.enviar("POST", "/api/consultas", corpo_consulta(), csrf=True)
    assert len(c.get_json("/api/consultas/minhas")) == 1
    repetido = c.enviar("POST", "/api/auth/registro", {"nome": "Ana", "email": "ANA.TESTE@exemplo.com",
                                                      "senha": "senha1234"}, csrf=True)
    assert repetido.status_code == 422
    assert c.enviar("POST", "/api/auth/logout", csrf=True).status_code == 204
    assert c.enviar("GET", "/api/auth/me").status_code == 204
    assert c.enviar("GET", "/api/consultas/minhas").status_code == 401


def test_10_login_com_senha_errada_responde_401_com_mensagem_generica(ambiente):
    c = Cliente(ambiente["base"])
    r = c.enviar("POST", "/api/auth/login", {"email": ADMIN_EMAIL, "senha": "errada123"}, csrf=True)
    assert r.status_code == 401
    assert "E-mail ou senha incorretos" in r.text
    inexistente = c.enviar("POST", "/api/auth/login", {"email": "ninguem@exemplo.com", "senha": "errada123"}, csrf=True)
    assert inexistente.status_code == 401
    assert inexistente.json()["detail"] == r.json()["detail"]


def test_11_migracao_do_historico_oficial_aplicada_na_inicializacao(ambiente):
    assert ambiente["historico_oficial"], "a migração V4 (base do Atlas Digital) deveria constar como aplicada"
    fontes = Cliente(ambiente["base"]).get_json("/api/fontes")
    assert "Atlas Digital de Desastres" in json.dumps(fontes, ensure_ascii=False)


def test_12_rota_segura_destino_obrigatorio_e_validacao_dos_parametros(ambiente):
    Estado.sgb = rs.sgb_sem_setores()
    apis = ambiente["apis"]
    c = Cliente(ambiente["base"])
    antes = apis.contar("/valhalla/route")
    r = c.get_json(f"/api/rotas/segura?lat={rs.LAT}&lon={rs.LON}&modo=A_PE&destLat=-29.9100&destLon=-51.1700")
    assert r["status"] == "ROTA_ENCONTRADA", r
    assert r["destino"]["latitude"] == pytest.approx(-29.91, abs=1e-9)
    assert r["trajeto"]["distanciaMetros"] == 260
    assert len(r["trajeto"]["coordenadas"]) == 3
    assert r["trajeto"]["instrucoes"][1]["texto"] == "Vire à esquerda na Rua do Morro."
    assert r["mensagem"].endswith("até o destino escolhido.")
    assert "193" in json.dumps(r["avisos"])
    assert "alternativas" not in r, "não há mais terreno alto automático"
    assert "escolhido" not in r["destino"]
    assert apis.contar("/valhalla/route") - antes == 1

    # O destino é obrigatório: sem ele (ou incompleto), resposta 400 com a explicação
    sem_destino = c.enviar("GET", "/api/rotas/segura?lat=-29.92&lon=-51.18")
    assert sem_destino.status_code == 400
    assert "Informe o destino" in sem_destino.json()["detail"]
    assert c.enviar("GET", "/api/rotas/segura?lat=-29.92&lon=-51.18&destLat=-29.91").status_code == 400
    fora = c.enviar("GET", "/api/rotas/segura?lat=40.7&lon=-74.0&destLat=40.71&destLon=-74.0")
    assert fora.status_code == 400
    assert "lat" in fora.json()["erros"]
    assert c.enviar("GET", "/api/rotas/segura?lat=-29.9&lon=-51.1&destLat=-29.91&destLon=-51.1&modo=AVIAO").status_code == 400
    assert c.enviar("GET", "/api/rotas/segura?lat=-29.9").status_code == 400


def test_13_rota_segura_com_andamento_em_tempo_real(ambiente):
    Estado.sgb = rs.sgb_sem_setores()
    base = ambiente["base"]
    cabecalhos = {"Accept": "text/event-stream, application/problem+json"}
    r = requests.get(f"{base}/api/rotas/segura/progresso?lat={rs.LAT}&lon={rs.LON}&destLat=-29.9100&destLon=-51.1700"
                     "&modo=CARRO", headers=cabecalhos, timeout=60)

    assert r.status_code == 200, r.text
    assert r.headers["Content-Type"].startswith("text/event-stream")
    assert r.headers["X-Accel-Buffering"] == "no"
    eventos = ler_eventos(r.content.decode("utf-8"))
    assert eventos[0][0] == "etapa"
    primeira = json.loads(eventos[0][1])
    assert (primeira["etapa"], primeira["estado"]) == ("ALTURA", "PENDENTE")
    assert "Copernicus" in primeira["fonte"]
    for etapa in ("ALTURA", "SETORES", "CAMINHO", "PERFIL"):
        assert any(f'"etapa": "{etapa}"' in dados and '"CONCLUIDA"' in dados for _, dados in eventos), etapa
    nome, dados = eventos[-1]
    assert nome == "resultado"
    rota = json.loads(dados)
    assert rota["status"] == "ROTA_ENCONTRADA"
    assert rota["modo"] == "CARRO"

    # Parâmetros inválidos: recusados antes do andamento, com a resposta de erro comum da API
    fora = requests.get(f"{base}/api/rotas/segura/progresso?lat=40.7&lon=-74.0&destLat=40.71&destLon=-74.0",
                        headers=cabecalhos, timeout=30)
    assert fora.status_code == 400
    assert "json" in fora.headers["Content-Type"]
    longe = requests.get(f"{base}/api/rotas/segura/progresso?lat=-29.92&lon=-51.18&destLat=-29.70&destLon=-51.18",
                         headers=cabecalhos, timeout=30)
    assert longe.status_code == 422, longe.text
    assert "até 20 km" in longe.json()["detail"]


def test_14_erros_comuns_no_formato_problem_details(ambiente):
    c = Cliente(ambiente["base"])
    nao_existe = c.enviar("GET", "/api/nao-existe")
    assert nao_existe.status_code == 404
    assert nao_existe.json()["title"] == "Não encontrado"
    assert c.enviar("GET", "/api/consultas/nao-e-uuid").status_code == 400
    assert c.enviar("GET", "/api/consultas/00000000-0000-0000-0000-000000000000").json()["detail"] == \
        "Consulta não encontrada."
    malformado = c.enviar("POST", "/api/ocorrencias", csrf=True, data="{nao e json", )
    assert malformado.status_code in (400, 415)
    texto = c.http.post(ambiente["base"] + "/api/ocorrencias", data="oi", headers={
        "X-XSRF-TOKEN": c.token(), "Content-Type": "text/plain"})
    assert texto.status_code == 415
    assert c.enviar("GET", "/api/ocorrencias?tamanho=500").json()["erros"] == {
        "tamanho": "deve ser menor que ou igual a 100"}
    assert c.enviar("GET", "/api/enderecos/cep/123").json()["erros"] == {"cep": "O CEP deve ter 8 dígitos."}
    assert c.enviar("GET", "/actuator/health").json() == {"status": "UP"}
    outra_origem = c.http.get(ambiente["base"] + "/api/fontes", headers={"Origin": "https://site-estranho.com"})
    assert outra_origem.status_code == 403


def test_15_site_e_descricao_da_api_servidos_pelo_mesmo_servidor(ambiente):
    c = Cliente(ambiente["base"])
    pagina = c.http.get(ambiente["base"] + "/", timeout=30)
    assert pagina.status_code == 200
    assert "text/html" in pagina.headers["Content-Type"]
    assert "AlertaLar" in pagina.text
    assert pagina.headers["Content-Security-Policy"].startswith("default-src 'self'")
    descricao = c.get_json("/api/openapi.json")
    assert {"/api/consultas", "/api/consultas/{id_consulta}", "/api/rotas/segura/progresso",
            "/api/admin/importacoes/registros-oficiais"} <= set(descricao["paths"])
    # Sem a página interativa, que dependeria de scripts de uma CDN
    assert c.enviar("GET", "/api/docs").status_code == 404


def test_20_nominatim_no_limite_o_endereco_e_encontrado_pelo_photon(ambiente):
    apis = ambiente["apis"]
    Estado.status_nominatim = 429
    try:
        c = Cliente(ambiente["base"])
        antes = apis.contar("/nominatim/search")
        r = c.get_json("/api/enderecos/buscar?rua=Rua%20de%20Teste&numero=210&cidade=Canoas&estado=RS")
        melhor = r["candidatos"][0]
        assert melhor["fonte"] == "Photon (OpenStreetMap)", r
        assert melhor["precisao"] == "NUMERO"
        assert melhor["suficienteParaAnalise"]
        assert apis.contar("/nominatim/search") - antes == 1, "uma recusa e o Nominatim entra em pausa"

        # Durante a pausa, a consulta completa também funciona, sem insistir no Nominatim
        consulta = c.enviar("POST", "/api/consultas", corpo_consulta(False, "220"), csrf=True)
        assert consulta.status_code == 201, consulta.text
        assert consulta.json()["endereco"]["precisao"] == "NUMERO"
        assert apis.contar("/nominatim/search") - antes == 1
        assert "PHOTON" in json.dumps(Cliente(ambiente["base"]).get_json("/api/fontes"))
    finally:
        Estado.status_nominatim = 200


def test_21_moderacao_so_relatos_mais_recente_primeiro_com_busca_e_rejeicao(ambiente):
    base = ambiente["base"]
    anonimo = Cliente(base)
    relato = {"localizacao": "Rua Dom João Becker, 1852", "municipio": "Canoas", "estado": "RS",
              "dataOcorrencia": "2026-10-20", "descricao": "Só um teste, 100% de água na rua.",
              "tipoEvento": "ALAGAMENTO", "latitude": rs.LAT + 0.002, "longitude": rs.LON,
              "declaracaoVeracidade": True}
    assert anonimo.enviar("POST", "/api/ocorrencias", relato, csrf=True).status_code == 201
    admin = Cliente(base)
    admin.login(ADMIN_EMAIL, ADMIN_SENHA)
    id_relato = admin.get_json("/api/admin/ocorrencias?status=PENDENTE")["itens"][0]["ocorrencia"]["id"]
    admin.enviar("PATCH", f"/api/admin/ocorrencias/{id_relato}/validacao", {"status": "CONFIRMADA"}, csrf=True)
    publicas_antes = anonimo.get_json("/api/ocorrencias")["total"]

    # Os registros oficiais (importados no teste anterior) não aparecem na moderação
    confirmados = admin.get_json("/api/admin/ocorrencias?status=CONFIRMADA")
    assert confirmados["total"] == 2, confirmados
    assert all(item["ocorrencia"]["origem"] == "RELATO_USUARIO" for item in confirmados["itens"])
    assert confirmados["itens"][0]["ocorrencia"]["id"] == id_relato, "o mais recente primeiro"

    # Busca por rua (com acento), por contato do relator e com curinga digitado
    por_rua = admin.get_json("/api/admin/ocorrencias?status=CONFIRMADA&busca=" + quote("dom JOÃO becker"))
    assert por_rua["total"] == 1, por_rua
    assert por_rua["itens"][0]["ocorrencia"]["id"] == id_relato
    assert admin.get_json("/api/admin/ocorrencias?status=CONFIRMADA&busca=morador%40exemplo")["total"] == 1
    assert admin.get_json("/api/admin/ocorrencias?status=CONFIRMADA&busca=100%25")["total"] == 1, "% é texto"
    assert admin.get_json("/api/admin/ocorrencias?status=CONFIRMADA&busca=_")["total"] == 0, "_ é texto"
    assert admin.enviar("GET", "/api/admin/ocorrencias?busca=" + "x" * 101).status_code == 400

    # Confirmado por engano: rejeitar tira da lista pública
    rejeitado = admin.enviar("PATCH", f"/api/admin/ocorrencias/{id_relato}/validacao",
                             {"status": "REJEITADA", "observacao": "teste"}, csrf=True)
    assert rejeitado.status_code == 200, rejeitado.text
    assert anonimo.get_json("/api/ocorrencias")["total"] == publicas_antes - 1
    assert admin.get_json("/api/admin/ocorrencias?status=REJEITADA")["total"] == 1

    # Usuário comum não entra na moderação
    comum = Cliente(base)
    comum.enviar("POST", "/api/auth/registro", {"nome": "Bia", "email": "bia@exemplo.com", "senha": "senha1234"},
                 csrf=True)
    assert comum.enviar("GET", "/api/admin/resumo").status_code == 403
