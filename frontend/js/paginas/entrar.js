// Login, cadastro e área da conta (histórico de consultas).
import { api } from '../api.js';
import { dadosFormulario, dataHora, el, iniciarCabecalho, limpar, mensagem, mostrarErrosCampos, usuarioLogado } from '../ui.js';

iniciarCabecalho();

const areaConta = document.getElementById('area-conta');
const areaAcesso = document.getElementById('area-acesso');

async function iniciar() {
  const u = await usuarioLogado();
  if (u) mostrarConta(u);
  else areaAcesso.classList.remove('oculto');
}

async function mostrarConta(u) {
  areaAcesso.classList.add('oculto');
  areaConta.classList.remove('oculto');
  document.getElementById('conta-nome').textContent = u.nome;
  document.getElementById('conta-email').textContent = u.email;
  if (u.papel === 'ADMIN') document.getElementById('link-painel').classList.remove('oculto');
  const c = document.getElementById('minhas-consultas');
  try {
    const lista = await api('/api/consultas/minhas');
    limpar(c);
    if (!lista.length) {
      c.append(el('p', { class: 'vazio' }, 'Você ainda não fez consultas com esta conta.'), el('a', { class: 'botao', href: '/#consultar' }, 'Consultar um endereço'));
      return;
    }
    c.append(el('ul', { class: 'lista-ocorrencias' }, lista.map((q) => el('li', {},
      el('span', { class: 'data' }, dataHora(q.dataConsulta)),
      el('span', { class: 'selo' }, q.rotulo),
      el('p', {}, el('a', { href: '/resultado.html?id=' + encodeURIComponent(q.id) }, q.endereco))))));
  } catch (e) {
    mensagem(c, 'erro', e.message);
  }
}

function destino() {
  const voltar = new URLSearchParams(location.search).get('voltar');
  return voltar && voltar.startsWith('/') && !voltar.startsWith('//') ? voltar : null;
}

document.getElementById('form-login').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = document.getElementById('msg-login');
  limpar(msg);
  try {
    await api('/api/auth/login', { metodo: 'POST', corpo: dadosFormulario(form) });
    if (destino()) location.href = destino();
    else location.reload();
  } catch (e) {
    if (e.status === 400) mostrarErrosCampos(form, e.erros);
    mensagem(msg, 'erro', e.message);
  }
});

document.getElementById('form-registro').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = document.getElementById('msg-registro');
  limpar(msg);
  try {
    await api('/api/auth/registro', { metodo: 'POST', corpo: dadosFormulario(form) });
    location.reload();
  } catch (e) {
    if (e.status === 400) mostrarErrosCampos(form, e.erros);
    mensagem(msg, 'erro', e.message);
  }
});

document.getElementById('botao-sair').addEventListener('click', async () => {
  try {
    await api('/api/auth/logout', { metodo: 'POST' });
  } finally {
    location.href = '/';
  }
});

iniciar();
