from alertalar.config import Configuracoes, converter_database_url, montar_url_sqlalchemy


def test_converte_a_connection_string_do_neon():
    p = converter_database_url("postgresql://neondb_owner:npg_Ab%40cd+1@ep-cool-123456-pooler.us-east-2.aws.neon.tech"
                               "/neondb?sslmode=require&channel_binding=require")
    assert p["DB_URL"] == "postgresql://ep-cool-123456-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    assert p["DB_USERNAME"] == "neondb_owner"
    assert p["DB_PASSWORD"] == "npg_Ab@cd+1"


def test_aceita_psql_aspas_porta_e_jdbc_e_ignora_o_que_nao_e_conexao():
    psql = converter_database_url("psql 'postgres://u:s@db.exemplo.com:6543/app'")
    assert psql["DB_URL"] == "postgresql://db.exemplo.com:6543/app?sslmode=require"
    assert psql["DB_PASSWORD"] == "s"
    assert converter_database_url("jdbc:postgresql://h/db?sslmode=require") == {
        "DB_URL": "jdbc:postgresql://h/db?sslmode=require"}
    assert converter_database_url("minha senha") == {}
    assert converter_database_url("mysql://u:s@h/db") == {}


def test_database_url_vale_so_quando_db_url_nao_foi_definida():
    c = Configuracoes.do_ambiente({"DATABASE_URL": "postgresql://u:segredo@h.neon.tech/neondb?sslmode=require"})
    assert c.db_url == "postgresql://h.neon.tech/neondb?sslmode=require"
    assert c.db_senha == "segredo"
    assert c.url_banco == "postgresql+psycopg://u:segredo@h.neon.tech/neondb?sslmode=require"

    com_db_url = Configuracoes.do_ambiente({"DATABASE_URL": "postgresql://u:segredo@h.neon.tech/neondb",
                                            "DB_URL": "jdbc:postgresql://outro/db"})
    assert com_db_url.db_url == "jdbc:postgresql://outro/db"
    assert com_db_url.url_banco.startswith("postgresql+psycopg://u:segredo@outro/db")

    sem = Configuracoes.do_ambiente({})
    assert sem.url_banco == "postgresql+psycopg://alertalar@localhost:5432/alertalar"


def test_senha_com_caracteres_especiais_vai_codificada_na_url():
    url = montar_url_sqlalchemy("jdbc:postgresql://localhost:5432/alertalar", "alertalar", "a@b:c/d")
    assert url == "postgresql+psycopg://alertalar:a%40b%3Ac%2Fd@localhost:5432/alertalar"


def test_user_agent_identifica_o_site_e_o_contato():
    c = Configuracoes.do_ambiente({"RENDER_EXTERNAL_URL": "https://alertalar.onrender.com",
                                   "ALERTALAR_CONTATO_EMAIL": "contato@exemplo.com"})
    assert c.user_agent == "AlertaLar/1.0 (+https://alertalar.onrender.com; contato@exemplo.com)"
    assert Configuracoes.do_ambiente({}).user_agent == "AlertaLar/1.0"


def test_proxy_e_cookie_seguro_vem_das_variaveis_do_render():
    c = Configuracoes.do_ambiente({"FORWARD_HEADERS_STRATEGY": "framework", "COOKIE_SECURE": "true",
                                   "ALERTALAR_CORS_ORIGENS": "https://a.com, https://b.com"})
    assert c.confiar_proxy and c.cookie_seguro
    assert c.cors_origens == ("https://a.com", "https://b.com")


def test_python_m_alertalar_sobe_um_unico_servidor_na_porta_do_ambiente(monkeypatch):
    import alertalar.__main__ as principal

    chamada = {}
    for chave in ("DATABASE_URL", "DB_URL", "FORWARD_HEADERS_STRATEGY"):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setattr(principal.uvicorn, "run", lambda app, **opcoes: chamada.update(app=app, **opcoes))
    principal.main()
    assert chamada["port"] == 9123
    assert chamada["host"] == "0.0.0.0"
    assert "workers" not in chamada
    assert chamada["proxy_headers"] is False and chamada["server_header"] is False
    assert any(getattr(r, "path", None) == "/actuator/health" for r in chamada["app"].routes)
    chamada["app"].state.servicos.encerrar()


def test_database_url_colada_com_prefixo_ou_quebrada_em_linhas_ainda_vale():
    for colada in ("DATABASE_URL=postgresql://u:s3nha@ep-x.us-east-1.aws.neon.tech/neondb?sslmode=require",
                   "postgresql://u:s3nha@ep-x.us-east-1.aws\n  .neon.tech/neondb?sslmode=require&channel_binding=require\n",
                   "export DATABASE_URL='postgresql://u:s3nha@ep-x.us-east-1.aws.neon.tech/neondb?sslmode=require'"):
        c = Configuracoes.do_ambiente({"DATABASE_URL": colada})
        assert c.db_url == "postgresql://ep-x.us-east-1.aws.neon.tech/neondb?sslmode=require"
        assert (c.db_usuario, c.db_senha) == ("u", "s3nha")
        assert c.descricao_banco == "ep-x.us-east-1.aws.neon.tech/neondb"
        assert c.origem_banco == "DATABASE_URL"


def test_database_url_errada_impede_o_inicio_com_mensagem_clara_e_sem_mostrar_a_senha():
    import pytest

    from alertalar.config import ConfiguracaoInvalida

    casos = {
        "neondb_owner npg_segredo123": "não começa com postgresql://",
        "postgresql://ep-x.neon.tech/neondb": "Falta o usuário e a senha",
        "postgresql://neondb_owner:****************@ep-x.neon.tech/neondb?sslmode=require": "asteriscos",
    }
    for valor, trecho in casos.items():
        with pytest.raises(ConfiguracaoInvalida) as erro:
            Configuracoes.do_ambiente({"DATABASE_URL": valor})
        assert trecho in str(erro.value)
        assert "segredo" not in str(erro.value)
    assert Configuracoes.do_ambiente({"DATABASE_URL": "lixo", "DB_URL": "postgresql://h/db"}).origem_banco == "DB_URL"
    assert Configuracoes.do_ambiente({}).origem_banco.startswith("nenhuma variável")
