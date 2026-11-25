// Rota segura: ponto de partida (localização, clique ou endereço) → caminho até o destino escolhido.
/* global L */
import { api, apiComAndamento } from '../api.js';
import { el, iniciarCabecalho, limpar, mensagem, preencherUfs, numero } from '../ui.js';
import { criarMapa, icone, popup } from '../mapa.js';
import { criarPainelProgresso } from '../progresso.js';

iniciarCabecalho();

const $ = (id) => document.getElementById(id);
const msg = $('msg-rota');
const botaoCalcular = $('botao-calcular');
const partidaTexto = $('partida-texto');
const formBusca = $('form-busca');
preencherUfs(formBusca.estado);

const mapa = criarMapa($('mapa-rota'));
const camadaResultado = L.layerGroup().addTo(mapa);
const painel = criarPainelProgresso($('progresso-mapa'));

// ---------------- Andamento: o que está sendo buscado agora ----------------
// Uma operação por vez (localização → endereço → rota). Começar outra cancela a anterior, e
// o botão "Cancelar" do painel interrompe tudo (o servidor também para de consultar as APIs).
let operacao = null;

function iniciarOperacao(titulo) {
  if (operacao) operacao.controle.abort();
  const op = { controle: new AbortController() };
  operacao = op;
  painel.abrir({ titulo, aoCancelar: () => cancelarOperacao(op) });
  return op;
}

/** Encerra a operação se ela ainda for a atual (false se foi cancelada ou substituída). */
function encerrarOperacao(op, { fechar = true } = {}) {
  if (operacao !== op) return false;
  operacao = null;
  if (fechar) painel.fechar();
  return true;
}

function cancelarOperacao(op) {
  op.controle.abort();
  if (!encerrarOperacao(op)) return;
  restaurarBotoes();
  mensagem(msg, 'info', 'Cancelado. Você pode tentar de novo quando quiser.');
}

/** A partida ou o destino mudou no meio do cálculo: a resposta antiga não serve mais. */
function descartarRotaEmCalculo() {
  const op = operacao;
  if (!op || !op.calculandoRota) return false;
  op.controle.abort();
  encerrarOperacao(op);
  restaurarBotoes();
  return true;
}

function restaurarBotoes() {
  botaoCalcular.disabled = !podeCalcular();
  botaoCalcular.textContent = 'Calcular rota segura';
  const local = $('botao-local');
  local.disabled = false;
  local.textContent = 'Usar minha localização';
  document.querySelectorAll('#form-busca button[type="submit"], #form-destino button[type="submit"]').forEach((b) => { b.disabled = false; });
}

/** No celular o mapa fica abaixo do formulário: traz o mapa para a tela para o painel ser visto. */
function mostrarMapa() {
  const r = $('mapa-rota').getBoundingClientRect();
  if (r.top > window.innerHeight - 120 || r.bottom < 80) {
    $('mapa-rota').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
  }
}

// Blocos do mapa (OpenStreetMap) demorando para chegar: aviso discreto no canto do mapa
const AvisoBlocos = L.Control.extend({
  options: { position: 'topright' },
  onAdd() {
    return L.DomUtil.create('div', 'aviso-blocos oculto');
  },
});
const avisoBlocos = new AvisoBlocos();
mapa.addControl(avisoBlocos);
mapa.eachLayer((camada) => {
  if (!(camada instanceof L.TileLayer)) return;
  let temporizadores = [];
  const caixa = avisoBlocos.getContainer();
  const esconder = () => {
    temporizadores.forEach(clearTimeout);
    temporizadores = [];
    caixa.classList.add('oculto');
  };
  const carregando = () => {
    esconder();
    temporizadores = [
      setTimeout(() => { caixa.textContent = 'Carregando o mapa…'; caixa.classList.remove('oculto'); }, 1500),
      setTimeout(() => { caixa.textContent = 'O mapa do OpenStreetMap está demorando para carregar. Verifique sua internet.'; }, 10000),
    ];
  };
  camada.on('loading', carregando);
  camada.on('load', esconder);
  if (camada.isLoading()) carregando(); // os primeiros blocos começaram a carregar antes deste ponto
});

let marcadorPartida = null;
let marcadorDestino = null;
let modo = 'A_PE';
let ultimaRota = null;

// ---------------- Onde a pessoa está (ponto azul) ----------------
// Atualizado continuamente enquanto a página está aberta, para acompanhar o caminho.
let pontoUsuario = null;
let circuloPrecisao = null;
let observador = null;

function mostrarUsuario(posicao) {
  const ll = L.latLng(posicao.coords.latitude, posicao.coords.longitude);
  const raio = Math.min(posicao.coords.accuracy || 0, 1500);
  if (!pontoUsuario) {
    circuloPrecisao = L.circle(ll, { radius: raio, className: 'precisao-usuario', interactive: false }).addTo(mapa);
    pontoUsuario = L.marker(ll, { icon: icone('usuario'), title: 'Você está aqui', keyboard: false, zIndexOffset: 1200 })
      .bindTooltip('Você está aqui').addTo(mapa);
  } else {
    pontoUsuario.setLatLng(ll);
    circuloPrecisao.setLatLng(ll).setRadius(raio);
  }
  return ll;
}

function acompanharUsuario() {
  if (observador !== null || !navigator.geolocation) return;
  observador = navigator.geolocation.watchPosition(mostrarUsuario, (erro) => {
    if (erro.code === erro.PERMISSION_DENIED) {
      navigator.geolocation.clearWatch(observador);
      observador = null;
    }
  }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 30000 });
}

// Botão no canto do mapa: centraliza no ponto azul (pede a localização se ainda não tiver)
const ControleLocalizacao = L.Control.extend({
  options: { position: 'topleft' },
  onAdd() {
    const caixa = L.DomUtil.create('div', 'leaflet-bar controle-localizacao');
    const botao = L.DomUtil.create('button', '', caixa);
    botao.type = 'button';
    botao.title = 'Mostrar onde estou';
    botao.setAttribute('aria-label', 'Mostrar onde estou no mapa');
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    [['circle', { cx: 12, cy: 12, r: 4, class: 'mira-centro' }], ['circle', { cx: 12, cy: 12, r: 8, class: 'mira-anel' }],
      ['path', { d: 'M12 1v4M12 19v4M1 12h4M19 12h4', class: 'mira-anel' }]].forEach(([tag, attrs]) => {
      const n = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
      svg.append(n);
    });
    botao.append(svg);
    L.DomEvent.disableClickPropagation(caixa);
    L.DomEvent.on(botao, 'click', () => centralizarNoUsuario(botao));
    return caixa;
  },
});
mapa.addControl(new ControleLocalizacao());

function centralizarNoUsuario(botao) {
  limpar(msg);
  if (pontoUsuario) {
    mapa.setView(pontoUsuario.getLatLng(), Math.max(mapa.getZoom(), 16));
    return;
  }
  if (!navigator.geolocation) {
    mensagem(msg, 'atencao', 'Este navegador não informa a localização.');
    return;
  }
  botao.disabled = true;
  navigator.geolocation.getCurrentPosition((p) => {
    botao.disabled = false;
    mapa.setView(mostrarUsuario(p), 16);
    acompanharUsuario();
  }, () => {
    botao.disabled = false;
    mensagem(msg, 'atencao', 'Não foi possível obter sua localização. Verifique se o navegador tem permissão para acessá-la.');
  }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
}

// Se a pessoa já autorizou a localização antes, o ponto azul aparece sem perguntar de novo
if (navigator.permissions && navigator.geolocation) {
  navigator.permissions.query({ name: 'geolocation' })
    .then((estado) => { if (estado.state === 'granted') acompanharUsuario(); })
    .catch(() => {});
}

// ---------------- Ponto de partida ----------------
let temporizadorRecalculo = null;

/**
 * Muda o ponto de partida. Se já havia uma rota na tela, ela é apagada na hora (nunca fica um
 * caminho saindo do ponto antigo) e uma nova é calculada a partir do novo ponto.
 */
function definirPartida(latlng, origem, descricao) {
  if (!marcadorPartida) {
    marcadorPartida = L.marker(latlng, { icon: icone('imovel'), draggable: true, title: 'Ponto de partida', zIndexOffset: 1000 }).addTo(mapa);
    marcadorPartida.on('dragend', () => definirPartida(marcadorPartida.getLatLng(), 'mapa'));
  } else {
    marcadorPartida.setLatLng(latlng);
  }
  const textoOrigem = descricao || { gps: 'sua localização', mapa: 'ponto marcado no mapa', endereco: 'endereço encontrado', link: 'endereço da consulta' }[origem] || 'ponto marcado';
  partidaTexto.textContent = `Ponto de partida: ${textoOrigem} (${latlng.lat.toFixed(5).replace('.', ',')}, ${latlng.lng.toFixed(5).replace('.', ',')}).`;
  $('remover-partida').hidden = false;
  botaoCalcular.disabled = false;
  if (origem !== 'endereco') marcarTratado(formBusca); // GPS ou mapa: o texto do campo não vale mais
  // Com o destino já escolhido, o caminho é calculado (e a rota antiga, se houver, some)
  if (descartarRotaEmCalculo() || ultimaRota || marcadorDestino) {
    apagarRota();
    clearTimeout(temporizadorRecalculo);
    temporizadorRecalculo = setTimeout(calcular, 500);
  }
}

/** Destino escolhido pela pessoa (endereço, nome do local ou ponto no mapa). */
function definirDestino(latlng, origem, descricao) {
  if (!marcadorDestino) {
    marcadorDestino = L.marker(latlng, { icon: icone('destino'), draggable: true, title: 'Destino', zIndexOffset: 950 }).addTo(mapa);
    marcadorDestino.on('dragend', () => definirDestino(marcadorDestino.getLatLng(), 'mapa'));
  } else {
    marcadorDestino.setLatLng(latlng);
    if (!mapa.hasLayer(marcadorDestino)) marcadorDestino.addTo(mapa);
  }
  const texto = descricao || (origem === 'mapa' ? 'ponto marcado no mapa' : 'endereço encontrado');
  $('destino-texto').textContent = `Destino: ${texto} (${latlng.lat.toFixed(5).replace('.', ',')}, ${latlng.lng.toFixed(5).replace('.', ',')}).`;
  $('remover-destino').hidden = false;
  if (origem !== 'endereco') marcarTratado(formDestino);
  // Com partida e destino definidos, o caminho já é calculado (e a rota antiga, se houver, some)
  if (marcadorPartida) {
    descartarRotaEmCalculo();
    apagarRota();
    mapa.fitBounds([marcadorPartida.getLatLng(), latlng], { padding: [50, 50], maxZoom: 16 });
    clearTimeout(temporizadorRecalculo);
    temporizadorRecalculo = setTimeout(calcular, 500);
  }
}

function apagarRota() {
  camadaResultado.clearLayers();
  $('resultado-rota').classList.add('oculto');
  ultimaRota = null;
}

/** Nome curto de um resultado do Nominatim: "Canoas Shopping, 6750, Avenida Guilherme Schell" */
function nomeCurto(enderecoEncontrado) {
  return (enderecoEncontrado || '').split(',').slice(0, 3).map((t) => t.trim()).filter(Boolean).join(', ');
}

// Marcar no mapa: o clique só marca um ponto depois que a pessoa pede ("Marcar no mapa"),
// para um toque sem querer no mapa não mudar a partida nem o destino.
let marcando = null; // 'partida' | 'destino' | null

function iniciarMarcacao(tipo) {
  marcando = tipo;
  limpar(msg);
  $('mapa-rota').classList.add('marcando');
  $('aviso-marcacao-texto').textContent = tipo === 'partida' ? 'Toque no mapa no ponto de partida.' : 'Toque no mapa no destino.';
  $('aviso-marcacao').classList.remove('oculto');
  $('mapa-rota').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
}

function encerrarMarcacao() {
  marcando = null;
  $('mapa-rota').classList.remove('marcando');
  $('aviso-marcacao').classList.add('oculto');
}

$('marcar-partida').addEventListener('click', () => iniciarMarcacao('partida'));
$('marcar-destino').addEventListener('click', () => iniciarMarcacao('destino'));
$('cancelar-marcacao').addEventListener('click', encerrarMarcacao);
document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && marcando) encerrarMarcacao(); });

mapa.on('click', (ev) => {
  if (!marcando) return;
  const tipo = marcando;
  encerrarMarcacao();
  if (tipo === 'destino') definirDestino(ev.latlng, 'mapa');
  else definirPartida(ev.latlng, 'mapa');
});

function removerPartida() {
  if (marcadorPartida) {
    mapa.removeLayer(marcadorPartida);
    marcadorPartida = null;
  }
  descartarRotaEmCalculo();
  clearTimeout(temporizadorRecalculo);
  apagarRota();
  partidaTexto.textContent = 'Ponto de partida ainda não definido.';
  $('remover-partida').hidden = true;
  botaoCalcular.disabled = !podeCalcular();
  limpar($('b-opcoes'));
}

function removerDestino() {
  if (marcadorDestino) {
    mapa.removeLayer(marcadorDestino);
    marcadorDestino = null;
  }
  descartarRotaEmCalculo();
  clearTimeout(temporizadorRecalculo);
  apagarRota();
  $('destino-texto').textContent = 'Destino ainda não definido. Busque acima ou marque no mapa.';
  $('remover-destino').hidden = true;
  limpar($('d-opcoes'));
}

$('remover-partida').addEventListener('click', removerPartida);
$('remover-destino').addEventListener('click', removerDestino);

// Texto digitado num campo de busca e ainda não buscado: buscado antes de calcular a rota
function chaveBusca(form) {
  return [form.rua.value.trim(), form.cidade.value.trim(), form.estado.value].join('|').toLowerCase();
}
function marcarTratado(form) {
  form.dataset.tratado = chaveBusca(form);
}
function textoPendente(form) {
  return form.rua.value.trim() !== '' && form.dataset.tratado !== chaveBusca(form);
}

// "Calcular" funciona com a partida marcada ou só com o endereço digitado (é buscado antes)
function podeCalcular() {
  return Boolean(marcadorPartida) || textoPendente(formBusca);
}
formBusca.addEventListener('input', () => { if (!operacao) botaoCalcular.disabled = !podeCalcular(); });

/** A cidade do destino costuma ser a da partida: preenche se a pessoa ainda não escreveu outra. */
function sugerirCidadeDoDestino() {
  if (!formDestino.cidade.value.trim() && formBusca.cidade.value.trim()) formDestino.cidade.value = formBusca.cidade.value.trim();
  if (!formDestino.estado.value && formBusca.estado.value) formDestino.estado.value = formBusca.estado.value;
}

/** Partida definida e ainda sem destino: convida a escolher o destino. */
function pedirDestino(texto, { focar = true } = {}) {
  mensagem(msg, 'info', texto);
  sugerirCidadeDoDestino();
  if (focar) formDestino.rua.focus({ preventScroll: true });
}

$('botao-local').addEventListener('click', () => {
  limpar(msg);
  if (!navigator.geolocation) {
    mensagem(msg, 'atencao', 'Este navegador não informa a localização. Clique no mapa onde você está ou busque um endereço.');
    return;
  }
  const botao = $('botao-local');
  botao.disabled = true;
  botao.textContent = 'Obtendo localização…';
  const op = iniciarOperacao(marcadorDestino ? 'Calculando a rota segura' : 'Obtendo sua localização');
  painel.etapa('GPS', {
    estado: 'EM_ANDAMENTO', rotulo: 'Sua localização', fonte: 'o GPS do aparelho',
    demora: { apos: 6000, texto: 'O GPS está demorando para achar o sinal. Perto de uma janela ou ao ar livre costuma ser mais rápido.' },
  });
  mostrarMapa();
  navigator.geolocation.getCurrentPosition(
    (p) => {
      if (operacao !== op) return; // cancelada ou substituída enquanto o GPS respondia
      botao.disabled = false;
      botao.textContent = 'Usar minha localização';
      painel.etapa('GPS', { estado: 'CONCLUIDA', detalhe: `precisão de cerca de ${Math.round(p.coords.accuracy)} m` });
      const ll = mostrarUsuario(p);
      acompanharUsuario();
      mapa.setView(ll, 16);
      definirPartida(ll, 'gps');
      if (marcadorDestino) {
        calcular({ continuar: true });
      } else {
        encerrarOperacao(op);
        restaurarBotoes();
        pedirDestino('Partida definida pela sua localização. Agora escolha para onde ir.');
      }
    },
    () => {
      if (!encerrarOperacao(op)) return;
      botao.disabled = false;
      botao.textContent = 'Usar minha localização';
      mensagem(msg, 'atencao', 'Não foi possível obter sua localização (permissão negada ou sinal fraco). Clique no mapa onde você está ou busque um endereço.');
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
});

/** Busca de endereço ou local, usada tanto para a partida quanto para o destino. */
const buscas = new Map();
function configurarBusca(form, opcoesEl, aoEscolher, rotulo) {
  buscas.set(form, { opcoesEl, aoEscolher, rotulo });
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    limpar(msg);
    if (!camposDeBuscaCompletos(form)) return;
    const op = iniciarOperacao('Buscando o endereço');
    if (await buscar(form, op)) encerrarOperacao(op);
  });
}

function camposDeBuscaCompletos(form) {
  if (form.rua.value.trim() && form.cidade.value.trim() && form.estado.value) return true;
  mensagem(msg, 'atencao', 'Para buscar, informe o endereço ou o nome do local, a cidade e o estado.');
  return false;
}

/**
 * Procura o texto do formulário e marca o lugar encontrado. Devolve true se deu certo; em caso de
 * erro mostra a mensagem e encerra a operação.
 */
async function buscar(form, op) {
  const { opcoesEl, aoEscolher, rotulo } = buscas.get(form);
  const rua = form.rua.value.trim();
  const cidade = form.cidade.value.trim();
  const estado = form.estado.value;
  limpar(opcoesEl);
  // "Rua das Flores, 120" → rua e número separados
  const m = rua.match(/^(.*?)[,\s]+(\d+[A-Za-z]?)\s*$/);
  const params = { rua: m ? m[1] : rua, numero: m ? m[2] : '', cidade, estado };
  const botao = form.querySelector('button[type="submit"]');
  const textoBotao = botao.textContent;
  botao.disabled = true;
  botao.textContent = 'Buscando…';
  const id = 'ENDERECO-' + form.id;
  painel.etapa(id, {
    estado: 'EM_ANDAMENTO', rotulo, fonte: 'o OpenStreetMap (Nominatim)', detalhe: `${rua}, ${cidade} - ${estado}`,
    demora: { apos: 8000, texto: 'O OpenStreetMap (Nominatim) está demorando. Esse serviço público atende um pedido por segundo e fica lento nos horários de muito uso.' },
  });
  try {
    const r = await api('/api/enderecos/buscar', { params, signal: op.controle.signal });
    if (operacao !== op) return false;
    marcarTratado(form);
    painel.etapa(id, { estado: 'CONCLUIDA', detalhe: nomeCurto(r.candidatos[0].enderecoEncontrado) });
    aoEscolher(r.candidatos[0]);
    // Mais de um lugar com esse nome (ex.: "Shopping"): deixa a pessoa escolher o certo
    const primeiro = nomeCurto(r.candidatos[0].enderecoEncontrado);
    const outros = r.candidatos.slice(1).filter((c, i, todos) => nomeCurto(c.enderecoEncontrado) !== primeiro
      && todos.findIndex((o) => nomeCurto(o.enderecoEncontrado) === nomeCurto(c.enderecoEncontrado)) === i);
    if (outros.length) {
      opcoesEl.append(el('p', { class: 'dica' }, 'Não é esse lugar? Escolha outro resultado:'),
        el('ul', { class: 'opcoes-busca' }, outros.map((c) => {
          const opcao = el('button', { type: 'button', class: 'opcao-busca' }, nomeCurto(c.enderecoEncontrado));
          opcao.addEventListener('click', () => {
            aoEscolher(c);
            opcoesEl.querySelectorAll('.opcao-busca').forEach((b) => b.removeAttribute('aria-current'));
            opcao.setAttribute('aria-current', 'true');
          });
          return el('li', {}, opcao);
        })));
    }
    return true;
  } catch (e) {
    if (e.name === 'AbortError' || !encerrarOperacao(op)) return false;
    restaurarBotoes();
    mensagem(msg, 'erro', e.message);
    return false;
  } finally {
    botao.disabled = false;
    botao.textContent = textoBotao;
  }
}

const formDestino = $('form-destino');
preencherUfs(formDestino.estado);
configurarBusca(formBusca, $('b-opcoes'), (c) => { escolherCandidato(c, definirPartida); sugerirCidadeDoDestino(); }, 'Endereço da partida');
configurarBusca(formDestino, $('d-opcoes'), (c) => escolherCandidato(c, definirDestino), 'Endereço do destino');

document.querySelectorAll('[data-modo]').forEach((b) => b.addEventListener('click', () => {
  modo = b.dataset.modo;
  document.querySelectorAll('[data-modo]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  if (ultimaRota) calcular();
}));

botaoCalcular.addEventListener('click', () => calcular());

function escolherCandidato(c, definir) {
  limpar(msg);
  const ll = L.latLng(c.latitude, c.longitude);
  mapa.setView(ll, 17);
  definir(ll, 'endereco', nomeCurto(c.enderecoEncontrado));
  if (!c.suficienteParaAnalise) {
    mensagem(msg, 'atencao', 'O lugar foi encontrado só de forma aproximada. Arraste o marcador até o ponto exato.');
  }
}

// ---------------- Cálculo ----------------
/**
 * @param {{continuar?: boolean}} opcoes  continuar: segue a operação já aberta no painel (depois do
 *   GPS ou da busca do endereço), mantendo as etapas que já apareceram.
 */
async function calcular({ continuar = false } = {}) {
  clearTimeout(temporizadorRecalculo);
  limpar(msg);
  encerrarMarcacao();
  const atual = continuar ? operacao : null;
  const desistir = (texto) => {
    if (atual) encerrarOperacao(atual);
    restaurarBotoes();
    if (texto) mensagem(msg, 'atencao', texto);
  };
  // Endereço digitado e ainda não buscado: busca primeiro (e calcula em seguida)
  const pendente = [formBusca, formDestino].find(textoPendente);
  if (pendente) {
    if (!camposDeBuscaCompletos(pendente)) {
      desistir();
      return;
    }
    const op = atual || iniciarOperacao('Calculando a rota segura');
    ocupado();
    mostrarMapa();
    if (await buscar(pendente, op)) calcular({ continuar: true });
    return;
  }
  if (!marcadorPartida) {
    desistir('Defina de onde você sai: use sua localização, busque um endereço ou clique no mapa.');
    return;
  }
  if (!marcadorDestino) {
    desistir();
    pedirDestino('Escolha o destino: busque o endereço ou o nome do local, ou marque no mapa.');
    return;
  }
  const p = marcadorPartida.getLatLng();
  const d = marcadorDestino.getLatLng();
  const params = { lat: p.lat.toFixed(6), lon: p.lng.toFixed(6), destLat: d.lat.toFixed(6), destLon: d.lng.toFixed(6), modo };
  const op = atual || iniciarOperacao('Calculando a rota segura');
  if (!atual) mostrarMapa();
  op.calculandoRota = true;
  ocupado();
  // Primeiro o próprio servidor precisa responder (no plano gratuito, ele "dorme" quando fica sem
  // uso); a linha some assim que ele responde e dá lugar às consultas que ele faz.
  painel.etapa('SERVIDOR', {
    estado: 'EM_ANDAMENTO', rotulo: 'Servidor do AlertaLar', detalhe: 'aguardando resposta',
    demora: { apos: 8000, texto: 'O servidor do AlertaLar está demorando para responder. Se o site ficou um tempo sem uso, ele pode levar cerca de 1 minuto para voltar.' },
  });
  try {
    const r = await apiComAndamento('/api/rotas/segura/progresso', {
      params,
      signal: op.controle.signal,
      aoConectar: () => { if (operacao === op) painel.remover('SERVIDOR'); },
      // Cada consulta externa feita pelo servidor: altura do terreno, áreas de risco, caminho e perfil
      aoEvento: (nome, e) => { if (nome === 'etapa' && operacao === op) painel.etapa(e.etapa, e); },
    });
    if (!encerrarOperacao(op)) return;
    ultimaRota = r;
    limpar(msg);
    renderizar(r);
  } catch (e) {
    if (e.name === 'AbortError' || !encerrarOperacao(op, { fechar: false })) return;
    // O servidor respondeu com um erro (a linha de espera sai) ou nem chegou a responder
    if (e.status) painel.remover('SERVIDOR');
    else if (painel.existe('SERVIDOR')) painel.etapa('SERVIDOR', { estado: 'FALHOU', detalhe: 'sem resposta' });
    painel.erro('Não foi possível calcular a rota', e.message, { aoTentarDeNovo: () => calcular() });
  } finally {
    if (!operacao) restaurarBotoes();
  }
}

function ocupado() {
  botaoCalcular.disabled = true;
  botaoCalcular.textContent = 'Calculando…';
}

function renderizar(r) {
  camadaResultado.clearLayers();
  const limites = [];
  (r.setoresRisco || []).forEach((s) => s.aneis.forEach((anel) => {
    L.polygon(anel, { color: '#c8372d', weight: 2, fillColor: '#c8372d', fillOpacity: 0.2 })
      .bindPopup(popup('Área de risco ' + (s.numero || ''), s.grau ? 'Grau: ' + s.grau : null, s.tipologia, 'Fonte: Serviço Geológico do Brasil'))
      .addTo(camadaResultado);
  }));
  limites.push([r.origem.latitude, r.origem.longitude]);

  if (r.trajeto) {
    L.polyline(r.trajeto.coordenadas, { color: '#ffffff', weight: 9, opacity: 0.9, interactive: false }).addTo(camadaResultado);
    L.polyline(r.trajeto.coordenadas, { color: '#12355b', weight: 5 }).bindTooltip('Caminho sugerido', { sticky: true }).addTo(camadaResultado);
    r.trajeto.coordenadas.forEach((c) => limites.push(c));
  }
  if (r.destino) limites.push([r.destino.latitude, r.destino.longitude]);
  const baixo = r.perfil && r.origem.elevacao !== null && r.perfil.elevacaoMinima < r.origem.elevacao - 2 && r.perfil.distanciaPontoMaisBaixo > 50;
  if (baixo) {
    L.marker(r.perfil.pontoMaisBaixo, { icon: icone('relato'), title: 'Trecho mais baixo do caminho' })
      .bindPopup(popup('Trecho mais baixo do caminho', `${Math.round(r.origem.elevacao - r.perfil.elevacaoMinima)} m abaixo da partida`, 'Não atravesse se estiver alagado'))
      .addTo(camadaResultado);
  }
  if (limites.length > 1) mapa.fitBounds(limites, { padding: [40, 40], maxZoom: 17 });
  else mapa.setView(limites[0], 16);

  const secao = $('resultado-rota');
  secao.classList.remove('oculto');
  $('t-resultado-rota').textContent = r.status === 'ROTA_ENCONTRADA' ? 'Rota sugerida' : 'Resultado';
  $('r-mensagem').textContent = r.mensagem;
  const medidas = limpar($('r-medidas'));
  if (r.trajeto) {
    medidas.append(...[
      medida(distancia(r.trajeto.distanciaMetros), 'de caminho'),
      medida(tempo(r.trajeto.duracaoSegundos), r.modo === 'A_PE' ? 'a pé' : 'de carro'),
      r.destino.ganhoElevacao === null ? null
        : Math.abs(r.destino.ganhoElevacao) < 1 ? medida('0 m', 'mesma altura da partida')
        : medida((r.destino.ganhoElevacao >= 0 ? '+' : '−') + Math.abs(Math.round(r.destino.ganhoElevacao)) + ' m',
          'de altura do destino em relação à partida')].filter(Boolean));
  }
  $('r-destino').textContent = r.destino ? r.destino.descricao : '';

  desenharPerfil(r);

  const avisos = limpar($('r-avisos'));
  r.avisos.forEach((a, i) => {
    const destaque = i < r.avisos.length - 2; // os dois últimos são orientações gerais
    avisos.append(el('div', { class: 'mensagem ' + (destaque ? 'mensagem-atencao' : '') }, el('p', {}, a)));
  });

  const lista = limpar($('r-instrucoes'));
  if (r.trajeto) {
    r.trajeto.instrucoes.forEach((i) => lista.append(el('li', {}, i.texto,
      i.distanciaMetros > 0 ? el('span', { class: 'dica' }, ' ' + distancia(i.distanciaMetros)) : null)));
  } else {
    lista.append(el('li', { class: 'vazio' }, 'Sem caminho calculado.'));
  }

  const abrir = $('r-abrir-mapas');
  if (r.destino) {
    const modoGoogle = r.modo === 'A_PE' ? 'walking' : 'driving';
    abrir.href = `https://www.google.com/maps/dir/?api=1&origin=${r.origem.latitude},${r.origem.longitude}&destination=${r.destino.latitude},${r.destino.longitude}&travelmode=${modoGoogle}`;
    abrir.classList.remove('oculto');
  } else {
    abrir.classList.add('oculto');
  }
  const fontes = limpar($('r-fontes'));
  r.fontes.forEach((f) => fontes.append(el('li', {}, f)));
  secao.focus({ preventScroll: true });
  secao.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
}

// Perfil de elevação em SVG (sem bibliotecas): linha do terreno e referência da altura da partida.
function desenharPerfil(r) {
  const bloco = $('r-perfil-bloco');
  const alvo = limpar($('r-perfil'));
  if (!r.perfil || !r.perfil.amostras || r.perfil.amostras.length < 2) {
    bloco.classList.add('oculto');
    return;
  }
  bloco.classList.remove('oculto');
  const ns = 'http://www.w3.org/2000/svg';
  // Largura real do bloco (em px) para o texto do gráfico não encolher no celular
  const L_ = Math.round(Math.min(720, Math.max(300, alvo.clientWidth - 16))); const A = 160; const M = { e: 44, d: 8, t: 10, b: 24 };
  const pts = r.perfil.amostras;
  const dMax = pts[pts.length - 1][0] || 1;
  const e0 = r.origem.elevacao;
  let eMin = Math.min(r.perfil.elevacaoMinima, e0);
  let eMax = Math.max(r.perfil.elevacaoMaxima, e0);
  if (eMax - eMin < 10) { eMax += 5; eMin -= 5; }
  const x = (d) => M.e + (d / dMax) * (L_ - M.e - M.d);
  const y = (e) => M.t + (1 - (e - eMin) / (eMax - eMin)) * (A - M.t - M.b);
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${L_} ${A}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Perfil de altura do caminho: de ${Math.round(pts[0][1])} m na partida a ${Math.round(pts[pts.length - 1][1])} m no destino, ponto mais baixo ${Math.round(r.perfil.elevacaoMinima)} m.`);
  const no = (tag, attrs) => { const n = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); svg.append(n); return n; };
  const area = [`M${x(pts[0][0])},${A - M.b}`].concat(pts.map((p) => `L${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`)).concat([`L${x(dMax)},${A - M.b}`, 'Z']).join(' ');
  no('path', { d: area, class: 'perfil-area' });
  no('polyline', { points: pts.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' '), class: 'perfil-linha' });
  no('line', { x1: M.e, x2: L_ - M.d, y1: y(e0), y2: y(e0), class: 'perfil-referencia' });
  const rotulo = (tx, px, py, anchor = 'start') => { const t = no('text', { x: px, y: py, 'text-anchor': anchor, class: 'perfil-texto' }); t.textContent = tx; };
  rotulo(`${Math.round(eMax)} m`, M.e - 6, M.t + 8, 'end');
  rotulo(`${Math.round(eMin)} m`, M.e - 6, A - M.b, 'end');
  rotulo('partida', M.e, A - 6);
  rotulo(distancia(dMax), L_ - M.d, A - 6, 'end');
  alvo.append(svg);
  $('r-perfil-legenda').textContent = `Linha tracejada: altura do ponto de partida (${Math.round(e0)} m). Fonte: Copernicus DEM GLO-90, com margem de erro de alguns metros.`;
}

function medida(valor, rotulo) {
  return el('div', { class: 'medida' }, el('strong', {}, valor), el('span', {}, rotulo));
}
function distancia(m) {
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${numero(m / 1000)} km`;
}
function tempo(s) {
  const min = Math.max(1, Math.round(s / 60));
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60} min`;
}

// Vindo do resultado de uma consulta: /rota.html?lat=..&lon=..
const params = new URLSearchParams(location.search);
const latP = parseFloat(params.get('lat'));
const lonP = parseFloat(params.get('lon'));
if (!Number.isNaN(latP) && !Number.isNaN(lonP)) {
  const ll = L.latLng(latP, lonP);
  mapa.setView(ll, 16);
  definirPartida(ll, 'link');
  pedirDestino('A partida é o endereço da sua consulta. Agora escolha para onde ir.', { focar: false });
}
