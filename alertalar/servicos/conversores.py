from __future__ import annotations

from alertalar.esquemas import (
    EnderecoResponse,
    FatorResponse,
    FonteResponse,
    OcorrenciaAdminResponse,
    OcorrenciaResponse,
    UsuarioResponse,
)
from alertalar.modelos.entidades import Endereco, FatorConsulta, FonteDados, Ocorrencia, Usuario
from alertalar.modelos.enums import OrigemOcorrencia
from alertalar.util.numeros import arredondar


def usuario(u: Usuario) -> UsuarioResponse:
    return UsuarioResponse(id=u.id, nome=u.nome, email=u.email, papel=u.papel.value)


def endereco(e: Endereco) -> EnderecoResponse:
    return EnderecoResponse(descricao=e.descricao_completa(), cep=e.cep, rua=e.rua, numero=e.numero, bairro=e.bairro,
                            cidade=e.cidade, estado=e.estado, codigo_ibge=e.codigo_ibge, latitude=e.latitude,
                            longitude=e.longitude, precisao=e.precisao.value, descricao_precisao=e.precisao.descricao,
                            fonte_geocodificacao=e.fonte_geocodificacao)


def fator(f: FatorConsulta) -> FatorResponse:
    return FatorResponse(codigo=f.codigo, nome=f.nome, categoria=f.categoria.value, situacao=f.situacao.value,
                         pontuacao=f.pontuacao, peso=f.peso, valor_observado=f.valor_observado,
                         explicacao=f.explicacao, fonte_codigo=None if f.fonte is None else f.fonte.codigo,
                         fonte_nome=None if f.fonte is None else f.fonte.nome, data_referencia=f.data_referencia)


def fonte(f: FonteDados) -> FonteResponse:
    return FonteResponse(codigo=f.codigo, nome=f.nome, tipo=f.tipo.value, url=f.url,
                         status_integracao=f.status_integracao.value, oficial=f.oficial,
                         data_atualizacao=f.data_atualizacao, descricao=f.descricao, atribuicao=f.atribuicao)


def ocorrencia(o: Ocorrencia, distancia_metros: float | None = None) -> OcorrenciaResponse:
    return OcorrenciaResponse(
        id=o.id, localizacao=o.localizacao, municipio=o.municipio, estado=o.estado, data_ocorrencia=o.data_ocorrencia,
        descricao=o.descricao, tipo_evento=o.tipo_evento.value, tipo_evento_rotulo=o.tipo_evento.rotulo,
        origem=o.origem.value,
        origem_rotulo="Registro oficial" if o.origem == OrigemOcorrencia.OFICIAL else "Relato de usuário validado",
        nivel_localizacao=o.nivel_localizacao.value, latitude=o.latitude, longitude=o.longitude,
        fonte=None if o.fonte is None else o.fonte.nome,
        distancia_metros=None if distancia_metros is None else float(arredondar(distancia_metros)),
        data_registro=o.data_registro)


def ocorrencia_admin(o: Ocorrencia) -> OcorrenciaAdminResponse:
    return OcorrenciaAdminResponse(ocorrencia=ocorrencia(o), status_validacao=o.status_validacao.value,
                                   nome_relator=o.nome_relator, contato_relator=o.contato_relator,
                                   observacao_validacao=o.observacao_validacao, data_validacao=o.data_validacao)
