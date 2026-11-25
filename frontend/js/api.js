// Cliente da API REST do AlertaLar (mesma origem). Envia o token CSRF nas requisições
// que alteram dados e converte respostas de erro (Problem Details) em ErroApi.

export class ErroApi extends Error {
  constructor(status, problema) {
    super((problema && (problema.detail || problema.title)) || mensagemPadrao(status));
    this.status = status;
    this.problema = problema || {};
    this.erros = (problema && problema.erros) || {};
  }
}

function mensagemPadrao(status) {
  if (status === 0) return 'Sem conexão com o servidor. Verifique sua internet e tente novamente.';
  if (status === 401) return 'Faça login para continuar.';
  if (status === 403) return 'Você não tem permissão para esta ação.';
  if (status === 404) return 'Não encontrado.';
  if (status === 429) return 'Muitas solicitações em pouco tempo. Aguarde um instante.';
  if (status >= 500) return 'O servidor não conseguiu concluir a solicitação. Tente novamente em instantes.';
  return 'Não foi possível concluir a solicitação.';
}

function lerCookie(nome) {
  const item = document.cookie.split('; ').find((c) => c.startsWith(nome + '='));
  return item ? decodeURIComponent(item.substring(nome.length + 1)) : null;
}

async function garantirTokenCsrf() {
  if (!lerCookie('XSRF-TOKEN')) {
    await fetch('/api/auth/csrf', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
  }
  return lerCookie('XSRF-TOKEN') || '';
}

function montarUrl(caminho, params) {
  let url = caminho;
  if (params) {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') p.append(k, v);
    });
    const qs = p.toString();
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }
  return url;
}

/** Pedido cancelado pela pessoa (AbortController): repassado como está, sem virar ErroApi. */
function cancelado(e) {
  return e && e.name === 'AbortError';
}

/**
 * @param {string} caminho  ex.: "/api/consultas"
 * @param {{metodo?: string, corpo?: any, formulario?: FormData, params?: object, signal?: AbortSignal}} opcoes
 */
export async function api(caminho, { metodo = 'GET', corpo, formulario, params, signal } = {}) {
  const url = montarUrl(caminho, params);
  const headers = { Accept: 'application/json' };
  const opcoes = { method: metodo, headers, credentials: 'same-origin', signal };
  if (metodo !== 'GET') {
    headers['X-XSRF-TOKEN'] = await garantirTokenCsrf();
  }
  if (corpo !== undefined) {
    headers['Content-Type'] = 'application/json';
    opcoes.body = JSON.stringify(corpo);
  } else if (formulario) {
    opcoes.body = formulario;
  }
  let resposta;
  try {
    resposta = await fetch(url, opcoes);
  } catch (e) {
    if (cancelado(e)) throw e;
    throw new ErroApi(0, null);
  }
  if (resposta.status === 204) return null;
  const tipo = resposta.headers.get('content-type') || '';
  const dados = tipo.includes('json') ? await resposta.json().catch((e) => { if (cancelado(e)) throw e; return null; }) : null;
  if (!resposta.ok) throw new ErroApi(resposta.status, dados);
  return dados;
}

/**
 * GET que acompanha o andamento no servidor (text/event-stream). Cada evento vira uma chamada a
 * aoEvento(nome, dados); o evento "resultado" é o valor devolvido e "erro" vira ErroApi.
 * aoConectar() é chamado quando o servidor responde (antes do primeiro evento).
 * Se a pessoa cancelar (signal), a promessa é rejeitada com o AbortError do navegador.
 *
 * @param {string} caminho
 * @param {{params?: object, signal?: AbortSignal, aoConectar?: Function, aoEvento?: Function}} opcoes
 */
export async function apiComAndamento(caminho, { params, signal, aoConectar, aoEvento } = {}) {
  let resposta;
  try {
    resposta = await fetch(montarUrl(caminho, params), {
      headers: { Accept: 'text/event-stream, application/problem+json' }, credentials: 'same-origin', signal,
    });
  } catch (e) {
    if (cancelado(e)) throw e;
    throw new ErroApi(0, null);
  }
  const tipo = resposta.headers.get('content-type') || '';
  if (!resposta.ok || !tipo.includes('text/event-stream')) {
    const dados = tipo.includes('json') ? await resposta.json().catch(() => null) : null;
    throw new ErroApi(resposta.ok ? 500 : resposta.status, dados);
  }
  if (aoConectar) aoConectar();

  let resultado;
  let erro;
  const tratarBloco = (bloco) => {
    let nome = 'message';
    const linhas = [];
    bloco.split('\n').forEach((linha) => {
      if (linha.startsWith('event:')) nome = linha.slice(6).trim();
      else if (linha.startsWith('data:')) linhas.push(linha.slice(5).replace(/^ /, ''));
    });
    if (!linhas.length) return;
    let dados;
    try {
      dados = JSON.parse(linhas.join('\n'));
    } catch {
      return;
    }
    if (nome === 'resultado') resultado = dados;
    else if (nome === 'erro') erro = new ErroApi(dados.status || 500, dados);
    else if (aoEvento) aoEvento(nome, dados);
  };

  let acumulado = '';
  const separar = (fim) => {
    acumulado = acumulado.replace(/\r\n/g, '\n');
    let i;
    while ((i = acumulado.indexOf('\n\n')) >= 0) {
      tratarBloco(acumulado.slice(0, i));
      acumulado = acumulado.slice(i + 2);
    }
    if (fim && acumulado.trim()) tratarBloco(acumulado);
  };
  try {
    if (resposta.body && resposta.body.getReader) {
      const leitor = resposta.body.getReader();
      const decodificador = new TextDecoder();
      for (;;) {
        const { done, value } = await leitor.read();
        if (done) break;
        acumulado += decodificador.decode(value, { stream: true });
        separar(false);
      }
      acumulado += decodificador.decode();
    } else {
      acumulado = await resposta.text(); // navegador sem leitura em partes: tudo chega no fim
    }
  } catch (e) {
    if (cancelado(e)) throw e;
    throw new ErroApi(0, { detail: 'A conexão com o servidor caiu antes do fim. Verifique sua internet e tente novamente.' });
  }
  separar(true);
  if (erro) throw erro;
  if (resultado === undefined) {
    throw new ErroApi(0, { detail: 'A conexão com o servidor caiu antes do fim. Verifique sua internet e tente novamente.' });
  }
  return resultado;
}
