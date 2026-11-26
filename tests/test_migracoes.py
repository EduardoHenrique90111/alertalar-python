import uuid

from sqlalchemy import create_engine, text

from alertalar import migracoes
from tests.apoio.banco import precisa_banco, url_banco_teste


def test_migracoes_disponiveis_em_ordem_e_sem_versao_repetida():
    lista = migracoes.disponiveis()
    assert [m.versao for m in lista] == [1, 2, 3, 4, 5]
    assert lista[3].tipo == "py"
    assert lista[0].descricao == "esquema inicial"


@precisa_banco
def test_banco_criado_pelo_flyway_nao_e_migrado_de_novo():
    esquema = "teste_" + uuid.uuid4().hex[:8]
    base = create_engine(url_banco_teste())
    with base.begin() as cx:
        cx.execute(text(f"CREATE SCHEMA {esquema}"))
    engine = create_engine(url_banco_teste(), connect_args={"options": f"-csearch_path={esquema}"})
    try:
        with engine.begin() as cx:
            cx.execute(text("""CREATE TABLE flyway_schema_history (installed_rank INT PRIMARY KEY, version VARCHAR(50),
                               description VARCHAR(200), script VARCHAR(1000), success BOOLEAN NOT NULL)"""))
            cx.execute(text("""INSERT INTO flyway_schema_history VALUES
                (1, '1', 'esquema inicial', 'V1__esquema_inicial.sql', true),
                (2, '2', 'fontes de dados', 'V2__fontes_de_dados.sql', true),
                (3, '3', 'chuvas intensas', 'V3__chuvas_intensas_e_fonte_rotas.sql', true),
                (4, '4', 'HistoricoOficialAtlas', 'com.alertalar.config.migracao.V4__HistoricoOficialAtlas', true),
                (5, '5', 'fonte photon', 'V5__fonte_photon.sql', true)"""))

        assert migracoes.aplicar(engine) == []

        with engine.connect() as cx:
            assert cx.execute(text("SELECT count(*) FROM historico_migracoes WHERE soma = 'flyway'")).scalar() == 5
            assert cx.execute(text("SELECT to_regclass('usuario')")).scalar() is None, "nada foi recriado"
    finally:
        engine.dispose()
        with base.begin() as cx:
            cx.execute(text(f"DROP SCHEMA {esquema} CASCADE"))
        base.dispose()
