"""Apoio aos testes: servidor HTTP falso, respostas simuladas e fábricas."""

from alertalar.integracoes.http import ClienteHttpExterno


def cliente_http(timeout_leitura: float = 3.0) -> ClienteHttpExterno:
    """O cliente HTTP real (mesma configuração da aplicação) para os testes de integração."""
    return ClienteHttpExterno("AlertaLar-Testes/1.0 (teste@alertalar.local)", 2.0, timeout_leitura)
