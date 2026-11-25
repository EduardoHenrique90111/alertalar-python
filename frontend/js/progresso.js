// Painel de andamento sobre o mapa: mostra o que está sendo consultado agora (e em qual
// serviço), quanto tempo cada etapa está levando e avisa quando alguma demora mais que o normal.
// As etapas vêm de acontecimentos reais (resposta do GPS, do servidor ou de cada API externa),
// nunca de uma estimativa de tempo.
import { el, limpar } from './ui.js';

const ATRASO_PARA_MOSTRAR = 300; // ms: operações rápidas terminam sem o painel piscar na tela
const DEMORA_PADRAO = 12000; // ms em uma mesma etapa até avisar que está demorando

/**
 * @param {HTMLElement} raiz  elemento vazio posicionado sobre o mapa
 */
export function criarPainelProgresso(raiz) {
  const regua = el('div', { class: 'regua', 'aria-hidden': 'true' }, el('div', { class: 'regua-agua' }));
  const titulo = el('p', { class: 'progresso-titulo', id: 'progresso-titulo' });
  const tempoTotal = el('span', { class: 'progresso-tempo', 'aria-hidden': 'true' });
  const lista = el('ol', { class: 'progresso-etapas' });
  const demora = el('p', { class: 'progresso-demora oculto' });
  const textoErro = el('p', { class: 'progresso-erro oculto', role: 'alert' });
  const botaoCancelar = el('button', { type: 'button', class: 'botao botao-secundario botao-pequeno' }, 'Cancelar');
  const botaoTentar = el('button', { type: 'button', class: 'botao botao-pequeno' }, 'Tentar de novo');
  const botaoFechar = el('button', { type: 'button', class: 'botao botao-secundario botao-pequeno' }, 'Fechar');
  const anuncio = el('p', { class: 'sr', 'aria-live': 'polite' });
  raiz.setAttribute('role', 'group');
  raiz.setAttribute('aria-labelledby', 'progresso-titulo');
  // Cancelar fica no topo e o aviso de demora logo abaixo: no celular o painel pode rolar
  raiz.append(
    el('div', { class: 'progresso-cabeca' }, regua, titulo, tempoTotal, botaoCancelar),
    demora, lista, textoErro,
    el('div', { class: 'progresso-acoes oculto' }, botaoTentar, botaoFechar),
    anuncio);
  const acoes = raiz.querySelector('.progresso-acoes');

  let etapas = new Map(); // id → { li, inicio, fim, estado, fonte, demora }
  let inicio = 0;
  let relogio = null;
  let atraso = null;
  let aoCancelar = null;
  let aoTentarDeNovo = null;
  let ultimaDemora = '';

  botaoCancelar.addEventListener('click', () => { if (aoCancelar) aoCancelar(); });
  botaoFechar.addEventListener('click', () => fechar());
  botaoTentar.addEventListener('click', () => {
    const repetir = aoTentarDeNovo;
    fechar();
    if (repetir) repetir();
  });

  function segundos(ms) {
    const s = Math.floor(ms / 1000);
    return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`;
  }

  function atualizarTempos() {
    const agora = Date.now();
    tempoTotal.textContent = segundos(agora - inicio);
    let maisDemorada = null;
    etapas.forEach((e) => {
      const tempo = e.li.querySelector('.etapa-tempo');
      if (e.estado === 'EM_ANDAMENTO') {
        const decorrido = agora - e.inicio;
        tempo.textContent = decorrido >= 2000 ? segundos(decorrido) : '';
        const limite = (e.demora && e.demora.apos) || DEMORA_PADRAO;
        if (decorrido >= limite && (!maisDemorada || decorrido - limite > maisDemorada.excesso)) {
          maisDemorada = { etapa: e, excesso: decorrido - limite };
        }
      }
    });
    const texto = maisDemorada ? textoDemora(maisDemorada.etapa) : '';
    demora.classList.toggle('oculto', !texto);
    if (texto !== ultimaDemora) {
      demora.textContent = texto;
      if (texto) anuncio.textContent = texto;
      ultimaDemora = texto;
    }
  }

  function textoDemora(e) {
    if (e.demora && e.demora.texto) return e.demora.texto;
    const fonte = e.fonte ? e.fonte.charAt(0).toUpperCase() + e.fonte.slice(1) : 'O serviço';
    return `${fonte} está demorando mais que o normal para responder. Você pode esperar ou cancelar e tentar de novo.`;
  }

  function mostrar() {
    clearTimeout(atraso);
    atraso = null;
    raiz.classList.remove('oculto');
  }

  /** Começa uma nova operação, com a lista de etapas vazia. */
  function abrir({ titulo: texto, aoCancelar: cancelar }) {
    aoCancelar = cancelar;
    aoTentarDeNovo = null;
    titulo.textContent = texto;
    raiz.classList.remove('com-erro');
    textoErro.classList.add('oculto');
    botaoCancelar.classList.remove('oculto');
    acoes.classList.add('oculto');
    etapas = new Map();
    limpar(lista);
    inicio = Date.now();
    ultimaDemora = '';
    demora.classList.add('oculto');
    clearInterval(relogio);
    relogio = setInterval(atualizarTempos, 500);
    atualizarTempos();
    if (raiz.classList.contains('oculto') && !atraso) atraso = setTimeout(mostrar, ATRASO_PARA_MOSTRAR);
  }

  /**
   * Cria ou atualiza uma etapa.
   * @param {string} id
   * @param {{estado: string, rotulo?: string, fonte?: string, detalhe?: string, demora?: {apos: number, texto: string}}} dados
   */
  function etapa(id, dados) {
    let e = etapas.get(id);
    if (!e) {
      const li = el('li', { class: 'progresso-etapa' },
        el('span', { class: 'etapa-icone', 'aria-hidden': 'true' }),
        el('span', { class: 'etapa-texto' },
          el('span', { class: 'etapa-rotulo' }),
          el('span', { class: 'sr etapa-estado' }),
          el('span', { class: 'etapa-fonte' }),
          el('span', { class: 'etapa-detalhe' })),
        el('span', { class: 'etapa-tempo', 'aria-hidden': 'true' }));
      e = { li, inicio: 0, fim: 0, estado: 'PENDENTE' };
      etapas.set(id, e);
      lista.append(li);
    }
    if (dados.rotulo) e.rotulo = dados.rotulo;
    if (dados.fonte) e.fonte = dados.fonte;
    if (dados.demora) e.demora = dados.demora;
    if (dados.detalhe !== undefined) e.detalhe = dados.detalhe || '';
    const anterior = e.estado;
    e.estado = dados.estado || e.estado;
    if (e.estado === 'EM_ANDAMENTO' && anterior !== 'EM_ANDAMENTO') e.inicio = Date.now();
    if ((e.estado === 'CONCLUIDA' || e.estado === 'FALHOU') && anterior !== e.estado) {
      e.fim = Date.now();
      if (!e.inicio) e.inicio = e.fim;
    }

    e.li.dataset.estado = e.estado;
    e.li.querySelector('.etapa-rotulo').textContent = e.rotulo || '';
    // Enquanto espera a resposta, mostra qual serviço está sendo consultado
    e.li.querySelector('.etapa-fonte').textContent = e.estado === 'EM_ANDAMENTO' && e.fonte ? `Consultando ${e.fonte}…` : '';
    e.li.querySelector('.etapa-detalhe').textContent = e.detalhe || '';
    const tempo = e.li.querySelector('.etapa-tempo');
    if (e.estado === 'CONCLUIDA' || e.estado === 'FALHOU') {
      const duracao = e.fim - e.inicio;
      tempo.textContent = duracao >= 1000 ? segundos(duracao) : '';
    } else if (e.estado === 'PENDENTE') {
      tempo.textContent = '';
    }
    e.li.querySelector('.etapa-estado').textContent =
      ` (${{ PENDENTE: 'a fazer', EM_ANDAMENTO: 'em andamento', CONCLUIDA: 'concluída', FALHOU: 'com problema' }[e.estado]})`;
    if (e.estado === 'EM_ANDAMENTO' && anterior !== 'EM_ANDAMENTO') {
      anuncio.textContent = `${e.rotulo}${e.fonte ? ` (consultando ${e.fonte})` : ''}…`;
    } else if (e.estado === 'FALHOU' && anterior !== 'FALHOU') {
      anuncio.textContent = `${e.rotulo}: ${e.detalhe || 'não foi possível concluir'}.`;
    }
    atualizarTempos();
  }

  /** Tira uma etapa da lista (ex.: a conexão com o servidor, depois que ele respondeu). */
  function remover(id) {
    const e = etapas.get(id);
    if (!e) return;
    e.li.remove();
    etapas.delete(id);
    atualizarTempos();
  }

  /** Mostra o erro no próprio painel, com as opções de tentar de novo ou fechar. */
  function erro(tituloErro, texto, { aoTentarDeNovo: repetir } = {}) {
    clearInterval(relogio);
    relogio = null;
    etapas.forEach((e, id) => { if (e.estado === 'EM_ANDAMENTO') etapa(id, { estado: 'FALHOU' }); });
    titulo.textContent = tituloErro;
    textoErro.textContent = texto;
    textoErro.classList.remove('oculto');
    demora.classList.add('oculto');
    raiz.classList.add('com-erro');
    aoTentarDeNovo = repetir || null;
    botaoCancelar.classList.add('oculto');
    acoes.classList.remove('oculto');
    botaoTentar.classList.toggle('oculto', !repetir);
    mostrar();
    (repetir ? botaoTentar : botaoFechar).focus({ preventScroll: true });
  }

  function fechar() {
    clearInterval(relogio);
    relogio = null;
    clearTimeout(atraso);
    atraso = null;
    raiz.classList.add('oculto');
    raiz.classList.remove('com-erro');
    aoCancelar = null;
    aoTentarDeNovo = null;
  }

  fechar();
  return { abrir, etapa, existe: (id) => etapas.has(id), remover, erro, fechar };
}
