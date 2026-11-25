// Lista pública de ocorrências confirmadas, com filtros, paginação e mapa.
/* global L */
import { api } from '../api.js';
import { data, dadosFormulario, el, iniciarCabecalho, limpar, mensagem, preencherUfs } from '../ui.js';
import { criarMapa, icone, popup } from '../mapa.js';

iniciarCabecalho();

const form = document.getElementById('form-filtros');
const lista = document.getElementById('o-lista');
const total = document.getElementById('o-total');
const anterior = document.getElementById('o-anterior');
const proxima = document.getElementById('o-proxima');
const indicadorPagina = document.getElementById('o-pagina');
preencherUfs(form.estado);

const mapa = criarMapa(document.getElementById('o-mapa'));
const camada = L.layerGroup().addTo(mapa);
let pagina = 0;
let filtros = {};

async function carregar() {
  limpar(lista);
  total.textContent = 'Carregando…';
  try {
    const r = await api('/api/ocorrencias', { params: { ...filtros, pagina, tamanho: 20 } });
    total.textContent = r.total === 0 ? '' : `${r.total} ocorrência(s) confirmada(s).`;
    if (!r.itens.length) {
      lista.append(el('li', { class: 'vazio' }, 'Nenhuma ocorrência confirmada encontrada com estes filtros.'));
    }
    camada.clearLayers();
    const pontos = [];
    r.itens.forEach((o) => {
      const oficial = o.origem === 'OFICIAL';
      lista.append(el('li', { class: oficial ? 'oficial' : '' },
        el('span', { class: 'data' }, data(o.dataOcorrencia)),
        el('span', { class: 'selo ' + (oficial ? 'selo-oficial' : 'selo-relato') }, o.origemRotulo),
        el('span', { class: 'selo' }, o.tipoEventoRotulo),
        el('p', {}, o.localizacao + (o.municipio ? ` (${o.municipio}/${o.estado})` : '')),
        el('p', { class: 'texto-secundario' }, o.descricao),
        el('p', { class: 'dica' }, 'Fonte: ' + o.fonte + (o.nivelLocalizacao === 'MUNICIPIO' ? '. Registro municipal, sem ponto exato.' : '.'))));
      if (o.latitude !== null) {
        pontos.push([o.latitude, o.longitude]);
        L.marker([o.latitude, o.longitude], { icon: icone(oficial ? 'oficial' : 'relato'), title: o.tipoEventoRotulo })
          .bindPopup(popup(o.tipoEventoRotulo + ' em ' + data(o.dataOcorrencia), o.origemRotulo, o.localizacao))
          .addTo(camada);
      }
    });
    if (pontos.length) mapa.fitBounds(pontos, { padding: [30, 30], maxZoom: 15 });
    indicadorPagina.textContent = r.totalPaginas > 0 ? `Página ${r.pagina + 1} de ${r.totalPaginas}` : '';
    anterior.disabled = r.pagina <= 0;
    proxima.disabled = r.pagina + 1 >= r.totalPaginas;
  } catch (e) {
    total.textContent = '';
    const caixa = el('li');
    lista.append(caixa);
    mensagem(caixa, 'erro', e.message);
  }
}

form.addEventListener('submit', (ev) => {
  ev.preventDefault();
  filtros = dadosFormulario(form);
  pagina = 0;
  carregar();
});
anterior.addEventListener('click', () => { pagina = Math.max(0, pagina - 1); carregar(); });
proxima.addEventListener('click', () => { pagina += 1; carregar(); });

carregar();
