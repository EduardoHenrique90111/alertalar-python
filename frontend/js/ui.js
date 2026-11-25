// Utilidades de interface compartilhadas por todas as páginas.
// Conteúdo vindo da API é sempre inserido com textContent (nunca innerHTML), evitando XSS.
import { api } from './api.js';

export const UFS = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR',
  'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'];

/** Cria um elemento: el('p', {class: 'x'}, 'texto', outroElemento) */
export function el(tag, atributos = {}, ...filhos) {
  const e = document.createElement(tag);
  Object.entries(atributos || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === false) return;
    if (k === 'class') e.className = v;
    else if (k === 'dataset') Object.assign(e.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.substring(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  });
  filhos.flat().forEach((f) => {
    if (f === undefined || f === null || f === false) return;
    e.append(f instanceof Node ? f : document.createTextNode(String(f)));
  });
  return e;
}

export function limpar(elemento) {
  while (elemento.firstChild) elemento.removeChild(elemento.firstChild);
  return elemento;
}

export function mensagem(container, tipo, texto, titulo) {
  limpar(container);
  container.classList.remove('oculto');
  const caixa = el('div', { class: 'mensagem mensagem-' + tipo, role: tipo === 'erro' ? 'alert' : 'status' },
    titulo ? el('p', {}, el('strong', {}, titulo)) : null,
    el('p', {}, texto));
  container.append(caixa);
  return caixa;
}

export function preencherUfs(select, selecionada) {
  if (!select) return;
  if (!select.querySelector('option')) select.append(el('option', { value: '' }, 'UF'));
  UFS.forEach((uf) => select.append(el('option', { value: uf, selected: uf === selecionada }, uf)));
}

/** Mostra erros de validação devolvidos pela API ao lado dos campos (atributo name). */
export function mostrarErrosCampos(form, erros = {}) {
  form.querySelectorAll('.erro-campo').forEach((e) => e.remove());
  form.querySelectorAll('.campo-invalido').forEach((e) => e.classList.remove('campo-invalido'));
  let primeiro = null;
  Object.entries(erros).forEach(([campo, texto]) => {
    const entrada = form.querySelector(`[name="${CSS.escape(campo)}"]`);
    if (!entrada) return;
    const caixa = entrada.closest('.campo') || entrada.parentElement;
    caixa.classList.add('campo-invalido');
    entrada.setAttribute('aria-invalid', 'true');
    caixa.append(el('span', { class: 'erro-campo' }, texto));
    primeiro = primeiro || entrada;
  });
  if (primeiro) primeiro.focus();
}

export function dadosFormulario(form) {
  const dados = {};
  new FormData(form).forEach((v, k) => {
    const valor = typeof v === 'string' ? v.trim() : v;
    dados[k] = valor === '' ? null : valor;
  });
  return dados;
}

const fmtData = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
const fmtDataHora = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const fmtNumero = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });

export function data(iso) {
  if (!iso) return '';
  const d = iso.length === 10 ? new Date(iso + 'T12:00:00') : new Date(iso);
  return fmtData.format(d);
}
export function dataHora(iso) { return iso ? fmtDataHora.format(new Date(iso)) : ''; }
export function numero(n) { return n === null || n === undefined ? '' : fmtNumero.format(n); }
export function metros(n) { return n === null || n === undefined ? '' : fmtNumero.format(Math.round(n)) + ' m'; }

let usuarioPromessa = null;
/** Usuário logado (ou null). */
export function usuarioLogado() {
  if (!usuarioPromessa) usuarioPromessa = api('/api/auth/me').catch(() => null);
  return usuarioPromessa;
}

/** Menu responsivo, link da conta e item "Moderação" para administradores. */
export async function iniciarCabecalho() {
  const botao = document.querySelector('.menu-botao');
  const menu = document.getElementById('menu');
  if (botao && menu) {
    botao.addEventListener('click', () => {
      const aberto = menu.classList.toggle('aberto');
      botao.setAttribute('aria-expanded', String(aberto));
    });
  }
  const caminho = location.pathname === '/' ? '/index.html' : location.pathname;
  document.querySelectorAll('.menu a').forEach((a) => {
    if (a.getAttribute('href') === caminho) a.setAttribute('aria-current', 'page');
  });
  const u = await usuarioLogado();
  const conta = document.querySelector('[data-link-conta]');
  if (u && conta) {
    conta.textContent = 'Minha conta';
    if (u.papel === 'ADMIN' && menu && !menu.querySelector('[data-link-painel]')) {
      const painel = el('a', { href: '/painel.html', 'data-link-painel': true }, 'Moderação');
      if (location.pathname === '/painel.html') painel.setAttribute('aria-current', 'page');
      conta.before(painel);
    }
  }
}
