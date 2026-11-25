"""Consulta (orquestração), relatos e moderação, importação oficial e situação atual, com dependências
simuladas."""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import ANY, Mock

import pytest

from alertalar.erros import IntegracaoExterna, RecursoNaoEncontrado, RegraNegocio
from alertalar.esquemas import EnderecoRequest, OcorrenciaRequest, ValidacaoRequest
from alertalar.integracoes.ibge import IbgeLocalidadesClient
from alertalar.integracoes.open_meteo import ClimaClient, SerieChuva
from alertalar.integracoes.s2id import LeitorRegistrosOficiaisCsv
from alertalar.modelos.entidades import Consulta, Endereco, FatorConsulta, FonteDados, Ocorrencia, Usuario
from alertalar.modelos.enums import (
    ClassificacaoRisco,
    NivelLocalizacao,
    OrigemOcorrencia,
    PapelUsuario,
    PrecisaoGeocodificacao,
    StatusIntegracao,
    StatusValidacao,
    TipoEvento,
    TipoFonte,
)
from alertalar.repositorios import ConsultaRepositorio, FonteDadosRepositorio, OcorrenciaRepositorio
from alertalar.servicos.analise.analise_risco import AnaliseRiscoService
from alertalar.servicos.analise.fatores import FatorProximidadeAgua, fatores_padrao
from alertalar.servicos.coleta import ColetaDadosService
from alertalar.servicos.consultas import ConsultaService, recortar
from alertalar.servicos.enderecos import EnderecoService
from alertalar.servicos.fontes import FonteDadosService
from alertalar.servicos.importacao import ImportacaoService
from alertalar.servicos.ocorrencias import OcorrenciaService, padrao_busca
from alertalar.servicos.situacao_atual import SituacaoAtualService
from tests.apoio.contexto import LAT, LON, ContextoTeste

# ---------------------------------------------------------------- consulta


def test_consulta_grava_classificacao_justificativa_fatores_com_fonte_e_mapa():
    e = Endereco(id=7, rua="Rua de Teste", cidade="Canoas", estado="RS", latitude=LAT, longitude=LON,
                 precisao=PrecisaoGeocodificacao.NUMERO)
    pedido = EnderecoRequest(rua="Rua de Teste", numero="100", cidade="Canoas", estado="RS")
    enderecos = Mock(spec=EnderecoService)
    enderecos.resolver_para_analise.return_value = e
    coleta = Mock(spec=ColetaDadosService)
    coleta.coletar.return_value = ContextoTeste.novo().rio_a(120).elevacao(4.0, 3.0, 120.0, 6.0).sem_setores().construir()
    fontes = Mock(spec=FonteDadosService)
    osm = FonteDados(id=4, codigo="OSM_CURSOS_AGUA", nome="OpenStreetMap", tipo=TipoFonte.BASE_GEOGRAFICA,
                     status_integracao=StatusIntegracao.ATIVA)
    fontes.listar.return_value = [osm]
    consultas = Mock(spec=ConsultaRepositorio)
    consultas.salvar.side_effect = lambda c: c

    ConsultaService(enderecos, coleta, AnaliseRiscoService(fatores_padrao()), consultas, fontes).realizar(pedido, None)

    enderecos.resolver_para_analise.assert_called_once_with(pedido)
    c: Consulta = consultas.salvar.call_args.args[0]
    assert c.classificacao == ClassificacaoRisco.ALTO
    assert c.endereco_id == 7
    assert len(c.fatores) == 5
    assert next(f for f in c.fatores if f.codigo == "PROXIMIDADE_AGUA").fonte_id == osm.id
    assert "Média ponderada" in c.justificativa
    mapa = json.loads(c.dados_mapa)
    assert len(mapa["cursosDagua"]) == 1
    assert mapa["aguaMaisProxima"]["distanciaMetros"] > 100


def test_consulta_inexistente_gera_nao_encontrado():
    consultas = Mock(spec=ConsultaRepositorio)
    consultas.com_endereco_e_fatores.return_value = None
    servico = ConsultaService(Mock(), Mock(), AnaliseRiscoService(fatores_padrao()), consultas, Mock())
    with pytest.raises(RecursoNaoEncontrado):
        servico.buscar(uuid.uuid4())


def test_recorte_de_linhas_mantem_apenas_os_trechos_perto_do_ponto():
    linha = [(LAT, LON + 0.001), (LAT, LON + 0.002), (LAT, LON + 0.5), (LAT, LON + 0.6)]
    trechos = recortar(linha, LAT, LON, 2000)
    assert len(trechos) == 1
    assert len(trechos[0]) == 3  # dois pontos internos + o ponto de saída


# ---------------------------------------------------------------- relatos e moderação

FONTE_RELATOS = FonteDados(id=8, codigo="ALERTALAR_RELATOS", nome="Relatos", tipo=TipoFonte.RELATO_USUARIO,
                           status_integracao=StatusIntegracao.ATIVA)


@pytest.fixture
def ocorrencias():
    class Ctx:
        repositorio = Mock(spec=OcorrenciaRepositorio)
        fontes = Mock(spec=FonteDadosService)
        ibge = Mock(spec=IbgeLocalidadesClient)
    c = Ctx()
    c.fontes.obrigatoria.side_effect = lambda codigo: FONTE_RELATOS if codigo == "ALERTALAR_RELATOS" else None
    c.repositorio.salvar.side_effect = lambda o: o
    c.ibge.codigo_municipio.side_effect = lambda uf, m: "4304606" if (uf, m) == ("RS", "Canoas") else None
    c.servico = OcorrenciaService(c.repositorio, c.fontes, c.ibge, Mock(spec=ColetaDadosService))
    return c


def relato(lat, lon):
    return OcorrenciaRequest(localizacao="Rua de Teste, 100", municipio="Canoas", estado="rs",
                             data_ocorrencia=date(2024, 5, 4),
                             descricao="A água chegou na altura do joelho e entrou nas casas.",
                             tipo_evento=TipoEvento.INUNDACAO, latitude=lat, longitude=lon, nome_relator="Maria",
                             contato_relator="maria@exemplo.com", declaracao_veracidade=True)


def test_relato_entra_como_pendente_de_usuario_com_ponto_quando_ha_coordenadas(ocorrencias):
    ocorrencias.servico.registrar_relato(relato(-29.92, -51.18), None)
    o: Ocorrencia = ocorrencias.repositorio.salvar.call_args.args[0]
    assert o.status_validacao == StatusValidacao.PENDENTE
    assert o.origem == OrigemOcorrencia.RELATO_USUARIO
    assert o.nivel_localizacao == NivelLocalizacao.PONTO
    assert o.estado == "RS"
    assert o.codigo_ibge == "4304606"
    assert o.fonte_id == FONTE_RELATOS.id


def test_sem_coordenadas_o_relato_fica_no_nivel_de_municipio(ocorrencias):
    ocorrencias.servico.registrar_relato(relato(None, None), None)
    assert ocorrencias.repositorio.salvar.call_args.args[0].nivel_localizacao == NivelLocalizacao.MUNICIPIO


def test_resposta_publica_nao_expoe_nome_nem_contato_do_relator(ocorrencias):
    texto = ocorrencias.servico.registrar_relato(relato(-29.92, -51.18), None).model_dump_json()
    assert "maria@exemplo.com" not in texto
    assert "Maria" not in texto


def test_administrador_confirma_relato_e_fica_registrado_quem_validou_e_quando(ocorrencias):
    o = Ocorrencia(id=10, origem=OrigemOcorrencia.RELATO_USUARIO, status_validacao=StatusValidacao.PENDENTE,
                   tipo_evento=TipoEvento.ALAGAMENTO, nivel_localizacao=NivelLocalizacao.PONTO, fonte=FONTE_RELATOS,
                   localizacao="Rua X", descricao="Água na rua", data_ocorrencia=date(2024, 5, 1))
    ocorrencias.repositorio.por_id.side_effect = lambda i: o if i == 10 else None
    admin = Usuario(id=1, nome="Admin", email="admin@exemplo.com", senha_hash="hash", papel=PapelUsuario.ADMIN)

    r = ocorrencias.servico.validar(10, ValidacaoRequest(status=StatusValidacao.CONFIRMADA,
                                                         observacao="Conferido com notícias locais"), admin)

    assert r.status_validacao == "CONFIRMADA"
    assert o.validado_por_id == admin.id
    assert o.data_validacao is not None
    ocorrencias.fontes.registrar_acesso.assert_called_once_with("ALERTALAR_RELATOS", ANY)


def test_registros_oficiais_nao_passam_por_moderacao(ocorrencias):
    ocorrencias.repositorio.por_id.return_value = Ocorrencia(origem=OrigemOcorrencia.OFICIAL)
    with pytest.raises(RegraNegocio):
        ocorrencias.servico.validar(5, ValidacaoRequest(status=StatusValidacao.REJEITADA), None)


def test_decisao_pendente_nao_e_aceita(ocorrencias):
    with pytest.raises(RegraNegocio):
        ocorrencias.servico.validar(1, ValidacaoRequest(status=StatusValidacao.PENDENTE), None)


def test_coordenadas_fora_do_brasil_sao_recusadas(ocorrencias):
    with pytest.raises(RegraNegocio):
        ocorrencias.servico.registrar_relato(relato(40.0, -74.0), None)


def test_busca_da_moderacao_em_minusculas_entre_porcentagens_sem_virar_curinga():
    assert padrao_busca("  Dom   João ") == "%dom joão%"
    assert padrao_busca("100% de água_x!") == "%100!% de água!_x!!%"
    assert padrao_busca("   ") is None
    assert padrao_busca(None) is None


# ---------------------------------------------------------------- importação oficial

def test_importa_como_oficial_confirmada_municipio_ignora_duplicados_e_atualiza_a_fonte():
    fonte = FonteDados(id=3, codigo="S2ID_RECONHECIMENTOS", nome="S2iD", tipo=TipoFonte.IMPORTACAO_OFICIAL,
                       status_integracao=StatusIntegracao.IMPORTACAO_MANUAL)
    fontes = Mock(spec=FonteDadosRepositorio)
    fontes.por_codigo.side_effect = lambda codigo: fonte if codigo == "S2ID_RECONHECIMENTOS" else None
    repositorio = Mock(spec=OcorrenciaRepositorio)
    repositorio.existe_identificador.side_effect = lambda fonte_id, ident: ident == "PROT:P-2"
    ibge = Mock(spec=IbgeLocalidadesClient)
    ibge.codigo_municipio.side_effect = lambda uf, m: "4304606" if (uf, m) == ("RS", "Canoas") else None
    csv = """Protocolo;UF;Município;Data do Evento;COBRADE
P-1;RS;Canoas;01/05/2024;1.2.1.0.0
P-2;RS;Canoas;02/05/2024;1.2.1.0.0
P-1;RS;Canoas;01/05/2024;1.2.1.0.0
"""
    servico = ImportacaoService(LeitorRegistrosOficiaisCsv(), repositorio, fontes, ibge)

    r = servico.importar_registros_oficiais(csv.encode("utf-8"), "s2id.csv", None)

    assert r.importados == 1
    assert r.duplicados == 2
    assert r.estados == ["RS"]
    o = repositorio.salvar_todas.call_args.args[0][0]
    assert o.origem == OrigemOcorrencia.OFICIAL
    assert o.status_validacao == StatusValidacao.CONFIRMADA
    assert o.nivel_localizacao == NivelLocalizacao.MUNICIPIO
    assert o.codigo_ibge == "4304606"
    assert o.identificador_externo == "PROT:P-1"
    assert "Importado da planilha \"s2id.csv\"" in o.descricao
    assert fonte.data_atualizacao is not None
    fontes.salvar.assert_called_once_with(fonte)


# ---------------------------------------------------------------- situação atual

AGORA = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)  # 07/11/2026 12:00 em Brasília
FUSO = timezone(timedelta(hours=-3))


def serie(mm_por_hora) -> SerieChuva:
    """Série horária de 80 h atrás até 96 h à frente; a função recebe a hora relativa a agora."""
    agora = AGORA.astimezone(FUSO).replace(tzinfo=None)
    horas = list(range(-80, 97))
    return SerieChuva(FUSO, [agora + timedelta(hours=h) for h in horas], [float(mm_por_hora(h)) for h in horas])


def consulta(classificacao: ClassificacaoRisco, pontuacao_agua: int) -> Consulta:
    c = Consulta(classificacao=classificacao)
    c.adicionar_fator(FatorConsulta(codigo=FatorProximidadeAgua.CODIGO, pontuacao=pontuacao_agua))
    return c


@pytest.fixture
def situacao():
    class Ctx:
        clima = Mock(spec=ClimaClient)
        consultas = Mock(spec=ConsultaRepositorio)
    c = Ctx()
    c.clima.vazao_diaria.side_effect = IntegracaoExterna("GloFAS", "sem rio")
    c.consultas.com_fatores.return_value = None
    c.servico = SituacaoAtualService(c.clima, Mock(spec=FonteDadosService), c.consultas, lambda: AGORA)
    return c


def test_soma_a_chuva_por_janela(situacao):
    # 1 mm/h entre 72 e 25 h atrás; 2 mm/h nas últimas 24 h; 3 mm/h nas próximas 24 h; 0,5 mm/h depois
    situacao.clima.chuva_horaria.return_value = serie(
        lambda h: 9 if h <= -72 else 1 if h <= -24 else 2 if h <= 0 else 3 if h <= 24 else 0.5)

    s = situacao.servico.consultar(LAT, LON)

    assert s.chuva.ultimas_24h_mm == 48.0
    assert s.chuva.ultimas_72h_mm == 48.0 + 48.0
    assert s.chuva.maior_intensidade_horaria_ultimas_24h_mm == 2.0
    assert s.chuva.proximas_24h_mm == 72.0
    assert s.chuva.maior_intensidade_horaria_proximas_24h_mm == 3.0
    assert s.chuva.maior_24h_entre_24e72h_mm == 12.0
    assert s.chuva.proximas_72h_mm == 72.0 + 24.0
    assert not s.vazao.disponivel
    assert s.risco_agora.nivel_chuva == 2, "72 mm previstos em 24 h = chuva forte"
    assert s.risco_agora.nivel == "ALTO", "sem consulta, suscetibilidade moderada"


def test_com_a_consulta_da_tela_local_de_alta_suscetibilidade_sem_chuva_fica_baixo(situacao):
    id_consulta = uuid.uuid4()
    situacao.clima.chuva_horaria.return_value = serie(lambda h: 0)
    situacao.consultas.com_fatores.side_effect = lambda i: consulta(ClassificacaoRisco.ALTO, 3) if i == id_consulta else None

    s = situacao.servico.consultar(LAT, LON, id_consulta)

    assert s.risco_agora.nivel == "BAIXO"
    assert s.risco_agora.suscetibilidade == "ALTO"


def test_mesma_chuva_locais_diferentes_e_a_chuva_vem_do_cache(situacao):
    alto, baixo = uuid.uuid4(), uuid.uuid4()
    situacao.clima.chuva_horaria.return_value = serie(lambda h: 1.5 if -24 < h <= 0 else 0)  # 36 mm em 24 h
    situacao.consultas.com_fatores.side_effect = lambda i: {alto: consulta(ClassificacaoRisco.ALTO, 0),
                                                            baixo: consulta(ClassificacaoRisco.BAIXO, 0)}.get(i)

    assert situacao.servico.consultar(LAT, LON, alto).risco_agora.nivel == "ALTO"
    assert situacao.servico.consultar(LAT, LON, baixo).risco_agora.nivel == "BAIXO"
    assert situacao.servico.consultar(LAT, LON, uuid.uuid4()).risco_agora.nivel == "ATENCAO", \
        "consulta inexistente = moderada"
    assert situacao.clima.chuva_horaria.call_count == 1


def test_fonte_de_chuva_fora_do_ar_deixa_o_risco_agora_indisponivel(situacao):
    situacao.clima.chuva_horaria.side_effect = IntegracaoExterna("Open-Meteo", "fora do ar")
    s = situacao.servico.consultar(LAT, LON)
    assert not s.chuva.disponivel
    assert s.chuva.motivo == "fora do ar"
    assert s.risco_agora.nivel == "INDISPONIVEL"
    assert s.chuva.ultimas_72h_mm is None
