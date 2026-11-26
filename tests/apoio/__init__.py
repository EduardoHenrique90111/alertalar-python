from alertalar.integracoes.http import ClienteHttpExterno


def cliente_http(timeout_leitura: float = 3.0) -> ClienteHttpExterno:
    return ClienteHttpExterno("AlertaLar-Testes/1.0 (teste@alertalar.local)", 2.0, timeout_leitura)
