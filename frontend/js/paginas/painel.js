// Moderação de relatos e importação de registros oficiais (somente administradores).
import { api } from '../api.js';
import { data, dataHora, el, iniciarCabecalho, limpar, mensagem, usuarioLogado } from '../ui.js';

iniciarCabecalho();

const lista = document.getElementById('p-lista');
const msg = document.getElementById('p-msg');
const anterior = document.getElementById('p-anterior');
const proxima = document.getElementById('p-proxima');
let status = 'PENDENTE';
let pagina = 0;
let busca = '';

async function iniciar() {
  const u = await usuarioLogado();
  if (!u || u.papel !== 'ADMIN') {
    const caixa = document.getElementById('p-sem-acesso');
    mensagem(caixa, 'atencao', u ? 'Sua conta não tem permissão de moderação.' : 'Entre com uma conta de administrador para acessar a moderação.');
    if (!u) caixa.append(el('a', { class: 'botao', href: '/entrar.html?voltar=/painel.html' }, 'Entrar'));
    return;
  }
  document.getElementById('p-conteudo').classList.remove('oculto');
  atualizarContador();
  carregar();
}

async function atualizarContador() {
  try {
    const r = await api('/api/admin/resumo');
    document.getElementById('p-contador').textContent = '(' + r.relatosPendentes + ')';
  } catch { /* contador é opcional */ }
}

let ultimoPedido = 0;
async function carregar() {
  const pedido = ++ultimoPedido;
  limpar(lista);
  lista.append(el('p', { class: 'vazio' }, 'Carregando…'));
  try {
    const r = await api('/api/admin/ocorrencias', { params: { status, busca, pagina, tamanho: 10 } });
    if (pedido !== ultimoPedido) return; // a pessoa já trocou de aba, de página ou de busca
    limpar(lista);
    const nome = { PENDENTE: 'aguardando verificação', CONFIRMADA: 'confirmado(s)', REJEITADA: 'rejeitado(s)' }[status];
    document.getElementById('p-total').textContent = busca
      ? `${r.total} relato(s) ${nome} com "${busca}".`
      : `${r.total} relato(s) ${nome}, do mais recente para o mais antigo.`;
    if (!r.itens.length) {
      lista.append(el('p', { class: 'vazio' }, busca ? 'Nenhum relato encontrado com essa busca nesta aba.'
        : status === 'PENDENTE' ? 'Nenhum relato aguardando verificação.' : 'Nenhum relato nesta situação.'));
    }
    r.itens.forEach((item) => lista.append(cartao(item)));
    document.getElementById('p-pagina').textContent = r.totalPaginas > 0 ? `Página ${r.pagina + 1} de ${r.totalPaginas}` : '';
    anterior.disabled = r.pagina <= 0;
    proxima.disabled = r.pagina + 1 >= r.totalPaginas;
  } catch (e) {
    if (pedido !== ultimoPedido) return;
    limpar(lista);
    mensagem(lista, 'erro', e.message);
  }
}

function cartao(item) {
  const o = item.ocorrencia;
  const observacao = el('textarea', { maxlength: '500', 'aria-label': 'Observação da moderação (opcional)', placeholder: 'Observação (opcional)' });
  observacao.value = item.observacaoValidacao || '';
  const mapaLink = o.latitude !== null
    ? el('a', { href: `https://www.openstreetmap.org/?mlat=${o.latitude}&mlon=${o.longitude}#map=18/${o.latitude}/${o.longitude}`, target: '_blank', rel: 'noopener' }, 'Ver posição no OpenStreetMap')
    : el('span', { class: 'dica' }, 'Sem coordenadas (registro municipal).');
  const decidir = async (novo) => {
    try {
      await api(`/api/admin/ocorrencias/${o.id}/validacao`, { metodo: 'PATCH', corpo: { status: novo, observacao: observacao.value.trim() || null } });
      mensagem(msg, 'sucesso', novo === 'CONFIRMADA' ? 'Relato confirmado. Ele agora conta na análise de risco.' : 'Relato rejeitado.');
      atualizarContador();
      carregar();
    } catch (e) {
      mensagem(msg, 'erro', e.message);
    }
  };
  return el('article', { class: 'relato-moderacao' },
    el('div', {},
      el('h3', {}, o.tipoEventoRotulo + ' em ' + data(o.dataOcorrencia),
        el('span', { class: 'selo ' + (item.statusValidacao === 'PENDENTE' ? 'selo-pendente' : '') }, item.statusValidacao.toLowerCase())),
      el('p', {}, o.localizacao + ' (' + o.municipio + '/' + o.estado + ')'),
      el('p', { class: 'texto-secundario' }, o.descricao),
      el('p', { class: 'dica' }, 'Enviado em ' + dataHora(o.dataRegistro)
        + (item.nomeRelator ? '. Relator: ' + item.nomeRelator : '. Relator não identificado')
        + (item.contatoRelator ? ' (' + item.contatoRelator + ')' : '') + '.'),
      mapaLink,
      observacao),
    // Só as decisões que mudam algo: um confirmado pode ser rejeitado, e um rejeitado, confirmado
    el('div', { class: 'acoes' },
      item.statusValidacao !== 'CONFIRMADA'
        ? el('button', { class: 'botao botao-pequeno', type: 'button', onclick: () => decidir('CONFIRMADA') }, 'Confirmar') : null,
      item.statusValidacao !== 'REJEITADA'
        ? el('button', { class: 'botao botao-perigo botao-pequeno', type: 'button', onclick: () => decidir('REJEITADA') }, 'Rejeitar') : null));
}

document.querySelectorAll('.abas button').forEach((b) => b.addEventListener('click', () => {
  document.querySelectorAll('.abas button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  status = b.dataset.status;
  pagina = 0;
  limpar(msg);
  carregar();
}));
// Busca por rua, cidade, descrição ou relator (vale para a aba aberta)
const formBusca = document.getElementById('p-busca');
const botaoLimpar = document.getElementById('p-limpar');
formBusca.addEventListener('submit', (ev) => {
  ev.preventDefault();
  busca = formBusca.busca.value.trim();
  botaoLimpar.hidden = !busca;
  pagina = 0;
  limpar(msg);
  carregar();
});
botaoLimpar.addEventListener('click', () => {
  formBusca.busca.value = '';
  busca = '';
  botaoLimpar.hidden = true;
  pagina = 0;
  carregar();
});
anterior.addEventListener('click', () => { pagina = Math.max(0, pagina - 1); carregar(); });
proxima.addEventListener('click', () => { pagina += 1; carregar(); });

document.getElementById('form-importar').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const saida = document.getElementById('msg-importar');
  const arquivo = document.getElementById('arquivo').files[0];
  if (!arquivo) {
    mensagem(saida, 'atencao', 'Selecione o arquivo CSV.');
    return;
  }
  const botao = document.getElementById('botao-importar');
  botao.disabled = true;
  botao.textContent = 'Importando…';
  try {
    const fd = new FormData();
    fd.append('arquivo', arquivo);
    const r = await api('/api/admin/importacoes/registros-oficiais', { metodo: 'POST', formulario: fd });
    const caixa = mensagem(saida, 'sucesso', `${r.importados} registro(s) importado(s) de ${r.linhasLidas} linha(s).`, 'Importação concluída');
    caixa.append(el('ul', {},
      el('li', {}, `Já existentes (ignorados): ${r.duplicados}`),
      el('li', {}, `Outros tipos de desastre (ignorados): ${r.ignoradosNaoHidrologicos}`),
      el('li', {}, `Linhas incompletas (ignoradas): ${r.invalidos}`),
      el('li', {}, `Sem código IBGE identificado: ${r.semCodigoIbge}`),
      el('li', {}, `Estados: ${r.estados.join(', ') || 'nenhum'}`)));
  } catch (e) {
    mensagem(saida, 'erro', e.message);
  } finally {
    botao.disabled = false;
    botao.textContent = 'Importar planilha';
  }
});

iniciar();
