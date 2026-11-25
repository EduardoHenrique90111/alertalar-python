// Página inicial: consulta em 3 etapas (endereço → confirmação no mapa → análise).
/* global L */
import { api, ErroApi } from '../api.js';
import { dadosFormulario, iniciarCabecalho, mensagem, mostrarErrosCampos, preencherUfs, limpar } from '../ui.js';
import { criarMapa, icone } from '../mapa.js';

iniciarCabecalho();

const form = document.getElementById('form-endereco');
const campoCep = document.getElementById('cep');
const statusCep = document.getElementById('cep-status');
const msgEndereco = document.getElementById('msg-endereco');
const msgConfirmacao = document.getElementById('msg-confirmacao');
const botaoLocalizar = document.getElementById('botao-localizar');
const botaoAnalisar = document.getElementById('botao-analisar');
const precisaoEl = document.getElementById('precisao');
const textoConfirmacao = document.getElementById('texto-confirmacao');
const coordenadasEl = document.getElementById('coordenadas');

preencherUfs(document.querySelector('[data-ufs]'));

let mapa = null;
let marcador = null;
let posicaoManual = false;
let precisaoSuficiente = false;
let enderecoAtual = null;

function irParaEtapa(n) {
  document.querySelectorAll('.etapa-consulta').forEach((e) => e.classList.toggle('ativa', e.dataset.etapa === String(n)));
  document.querySelectorAll('.passos-consulta li').forEach((li) => {
    const p = Number(li.dataset.passo);
    li.classList.toggle('feito', p < n);
    li.classList.toggle('atual', p === n);
  });
  if (n === 2 && mapa) setTimeout(() => mapa.invalidateSize(), 50);
}

// ---------- CEP: preenchimento automático ----------
campoCep.addEventListener('input', () => {
  let d = campoCep.value.replace(/\D/g, '').slice(0, 8);
  if (d.length > 5) d = d.slice(0, 5) + '-' + d.slice(5);
  campoCep.value = d;
  if (d.length === 9) buscarCep(d);
});

async function buscarCep(cep) {
  statusCep.textContent = 'Buscando CEP…';
  try {
    const r = await api('/api/enderecos/cep/' + encodeURIComponent(cep));
    if (r.rua) form.rua.value = r.rua;
    if (r.bairro) form.bairro.value = r.bairro;
    form.cidade.value = r.cidade || '';
    form.estado.value = r.estado || '';
    statusCep.textContent = 'Endereço preenchido pelo CEP. Confira e informe o número.';
    form.numero.focus();
  } catch (e) {
    statusCep.textContent = e.status === 404 ? 'CEP não encontrado. Preencha o endereço manualmente.' : e.message;
  }
}

// ---------- Etapa 1 → 2: localizar ----------
form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  limpar(msgEndereco);
  const dados = dadosFormulario(form);
  const errosLocais = {};
  if (!dados.rua) errosLocais.rua = 'Informe a rua ou avenida.';
  if (!dados.cidade) errosLocais.cidade = 'Informe a cidade.';
  if (!dados.estado) errosLocais.estado = 'Selecione o estado.';
  mostrarErrosCampos(form, errosLocais);
  if (Object.keys(errosLocais).length) return;

  enderecoAtual = dados;
  botaoLocalizar.disabled = true;
  botaoLocalizar.textContent = 'Localizando…';
  try {
    const r = await api('/api/enderecos/buscar', { params: dados });
    const melhor = r.candidatos[0];
    precisaoSuficiente = melhor.suficienteParaAnalise;
    prepararMapa([melhor.latitude, melhor.longitude], precisaoSuficiente ? 18 : 15);
    precisaoEl.textContent = melhor.descricaoPrecisao;
    precisaoEl.classList.toggle('precisao-baixa', !precisaoSuficiente);
    textoConfirmacao.textContent = r.mensagem;
    irParaEtapa(2);
  } catch (e) {
    if (e instanceof ErroApi && e.status === 400) {
      mostrarErrosCampos(form, e.erros);
      mensagem(msgEndereco, 'erro', e.message);
    } else if (e.status === 404 || e.status === 503) {
      // Não achou, ou a busca de endereços está fora do ar: a pessoa ainda pode marcar no mapa
      const caixa = mensagem(msgEndereco, 'atencao', e.message,
        e.status === 404 ? 'Endereço não localizado' : 'Busca de endereços indisponível agora');
      const marcar = document.createElement('button');
      marcar.type = 'button';
      marcar.className = 'botao botao-secundario botao-pequeno';
      marcar.textContent = 'Marcar a posição no mapa';
      marcar.addEventListener('click', () => {
        precisaoSuficiente = false;
        prepararMapa(null, 4);
        precisaoEl.textContent = 'Posição ainda não marcada';
        precisaoEl.classList.add('precisao-baixa');
        textoConfirmacao.textContent = 'Aproxime o mapa até o imóvel e clique sobre ele para marcar a posição.';
        irParaEtapa(2);
      });
      caixa.append(marcar);
    } else {
      mensagem(msgEndereco, 'erro', e.message);
    }
  } finally {
    botaoLocalizar.disabled = false;
    botaoLocalizar.textContent = 'Localizar no mapa';
  }
});

function prepararMapa(posicao, zoom) {
  posicaoManual = false;
  irParaEtapa(2);
  if (!mapa) {
    mapa = criarMapa(document.getElementById('mapa-confirmacao'));
    mapa.on('click', (ev) => definirPosicao(ev.latlng, true));
  }
  if (marcador) {
    marcador.remove();
    marcador = null;
  }
  limpar(msgConfirmacao);
  if (posicao) {
    mapa.setView(posicao, zoom);
    definirPosicao(L.latLng(posicao[0], posicao[1]), false);
  } else {
    mapa.setView([-15.8, -47.9], zoom);
    coordenadasEl.textContent = '';
  }
}

function definirPosicao(latlng, manual) {
  if (!marcador) {
    marcador = L.marker(latlng, { icon: icone('imovel'), draggable: true, keyboard: true, title: 'Posição do imóvel' }).addTo(mapa);
    marcador.on('dragend', () => definirPosicao(marcador.getLatLng(), true));
  } else {
    marcador.setLatLng(latlng);
  }
  if (manual) {
    posicaoManual = true;
    precisaoEl.textContent = 'Posição marcada por você no mapa';
    precisaoEl.classList.remove('precisao-baixa');
  }
  coordenadasEl.textContent = `Latitude ${numeroFixo(latlng.lat)}, longitude ${numeroFixo(latlng.lng)}`;
}

const numeroFixo = (v) => v.toFixed(5).replace('.', ',');

document.getElementById('botao-voltar').addEventListener('click', () => irParaEtapa(1));

// ---------- Etapa 2 → 3: analisar ----------
botaoAnalisar.addEventListener('click', async () => {
  limpar(msgConfirmacao);
  if (!marcador) {
    mensagem(msgConfirmacao, 'atencao', 'Clique no mapa sobre o imóvel para marcar a posição antes de analisar.');
    return;
  }
  if (!precisaoSuficiente && !posicaoManual) {
    mensagem(msgConfirmacao, 'atencao', 'A localização encontrada é aproximada. Clique no mapa sobre o imóvel para confirmar a posição exata.');
    return;
  }
  const corpo = { ...enderecoAtual };
  if (posicaoManual) {
    const p = marcador.getLatLng();
    corpo.latitude = Number(p.lat.toFixed(6));
    corpo.longitude = Number(p.lng.toFixed(6));
  }
  irParaEtapa(3);
  const frases = ['Consultando rios, relevo e registros de ocorrências…', 'Verificando áreas de risco mapeadas…',
    'Calculando a elevação relativa do terreno…', 'Montando a explicação do resultado…'];
  let i = 0;
  const textoCarregando = document.getElementById('texto-carregando');
  const intervalo = setInterval(() => { i = (i + 1) % frases.length; textoCarregando.textContent = frases[i]; }, 3500);
  try {
    const r = await api('/api/consultas', { metodo: 'POST', corpo });
    location.href = '/resultado.html?id=' + encodeURIComponent(r.id);
  } catch (e) {
    irParaEtapa(2);
    if (e.problema && e.problema.codigo === 'PRECISAO_INSUFICIENTE') {
      precisaoSuficiente = false;
      mensagem(msgConfirmacao, 'atencao', e.message);
    } else if (e.status === 400) {
      irParaEtapa(1);
      mostrarErrosCampos(form, e.erros);
      mensagem(msgEndereco, 'erro', e.message);
    } else {
      mensagem(msgConfirmacao, 'erro', e.message);
    }
  } finally {
    clearInterval(intervalo);
  }
});

