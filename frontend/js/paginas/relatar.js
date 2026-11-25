// Formulário de relato de alagamento (fica pendente até a moderação validar).
/* global L */
import { api } from '../api.js';
import { dadosFormulario, el, iniciarCabecalho, limpar, mensagem, mostrarErrosCampos, preencherUfs } from '../ui.js';
import { criarMapa, icone } from '../mapa.js';

iniciarCabecalho();

const form = document.getElementById('form-relato');
const msg = document.getElementById('msg-relato');
const posicaoTexto = document.getElementById('posicao-relato');
const botaoEnviar = document.getElementById('botao-enviar');
const params = new URLSearchParams(location.search);

preencherUfs(form.estado, params.get('estado'));
if (params.get('municipio')) form.municipio.value = params.get('municipio');
form.dataOcorrencia.max = new Date().toISOString().slice(0, 10);

const mapa = criarMapa(document.getElementById('mapa-relato'));
let marcador = null;

function definirPosicao(latlng) {
  if (!marcador) {
    marcador = L.marker(latlng, { icon: icone('relato'), draggable: true, title: 'Local da ocorrência' }).addTo(mapa);
    marcador.on('dragend', () => definirPosicao(marcador.getLatLng()));
  } else {
    marcador.setLatLng(latlng);
  }
  posicaoTexto.textContent = `Posição marcada: latitude ${latlng.lat.toFixed(5).replace('.', ',')}, longitude ${latlng.lng.toFixed(5).replace('.', ',')}.`;
}

mapa.on('click', (ev) => definirPosicao(ev.latlng));

const lat = parseFloat(params.get('lat'));
const lon = parseFloat(params.get('lon'));
if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
  mapa.setView([lat, lon], 17);
  definirPosicao(L.latLng(lat, lon));
}

document.getElementById('botao-localizacao').addEventListener('click', () => {
  if (!navigator.geolocation) {
    mensagem(msg, 'atencao', 'Seu navegador não permite obter a localização. Marque o ponto clicando no mapa.');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (p) => {
      const ll = L.latLng(p.coords.latitude, p.coords.longitude);
      mapa.setView(ll, 17);
      definirPosicao(ll);
      limpar(msg);
    },
    () => mensagem(msg, 'atencao', 'Não foi possível obter sua localização. Marque o ponto clicando no mapa.'),
    { enableHighAccuracy: true, timeout: 10000 });
});

document.getElementById('botao-remover-posicao').addEventListener('click', () => {
  if (marcador) marcador.remove();
  marcador = null;
  posicaoTexto.textContent = 'Nenhuma posição marcada.';
});

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  limpar(msg);
  const dados = dadosFormulario(form);
  dados.declaracaoVeracidade = form.declaracaoVeracidade.checked;
  if (marcador) {
    const p = marcador.getLatLng();
    dados.latitude = Number(p.lat.toFixed(6));
    dados.longitude = Number(p.lng.toFixed(6));
  }
  botaoEnviar.disabled = true;
  try {
    await api('/api/ocorrencias', { metodo: 'POST', corpo: dados });
    mostrarErrosCampos(form, {});
    form.reset();
    if (marcador) marcador.remove();
    marcador = null;
    posicaoTexto.textContent = 'Nenhuma posição marcada.';
    const caixa = mensagem(msg, 'sucesso', 'Relato enviado. Ele será verificado pela moderação antes de aparecer na lista de ocorrências.', 'Obrigado!');
    caixa.append(el('p', {}, el('a', { href: '/ocorrencias.html' }, 'Ver ocorrências registradas')));
    caixa.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (e) {
    if (e.status === 400) mostrarErrosCampos(form, e.erros);
    mensagem(msg, 'erro', e.message);
  } finally {
    botaoEnviar.disabled = false;
  }
});
