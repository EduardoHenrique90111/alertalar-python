// Helpers do mapa (Leaflet + blocos do OpenStreetMap).
// Política de uso dos blocos: https://operations.osmfoundation.org/policies/tiles/
/* global L */

export const CENTRO_BRASIL = [-15.8, -47.9];

export function criarMapa(elemento, { centro = CENTRO_BRASIL, zoom = 4 } = {}) {
  const mapa = L.map(elemento, { scrollWheelZoom: false }).setView(centro, zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">Colaboradores do OpenStreetMap</a>',
  }).addTo(mapa);
  // Zoom pela roda do mouse só depois que a pessoa interage com o mapa (não "prende" a rolagem da página)
  mapa.on('click focus', () => mapa.scrollWheelZoom.enable());
  mapa.on('mouseout blur', () => mapa.scrollWheelZoom.disable());
  return mapa;
}

/** Marcadores em CSS (sem imagens externas nem estilos inline). tipo: imovel | destino | oficial | relato | agua | usuario */
export function icone(tipo) {
  const pino = tipo === 'imovel' || tipo === 'destino';
  const tamanho = pino ? 30 : tipo === 'usuario' ? 20 : 18;
  return L.divIcon({
    className: 'marcador marcador-' + tipo,
    html: '<span></span>',
    iconSize: [tamanho, tamanho],
    iconAnchor: pino ? [tamanho / 2, tamanho] : [tamanho / 2, tamanho / 2],
    popupAnchor: [0, -tamanho / 2],
  });
}

/** Conteúdo de popup montado com nós DOM (texto da API nunca vira HTML). */
export function popup(...linhas) {
  const div = document.createElement('div');
  linhas.filter(Boolean).forEach((l, i) => {
    const p = document.createElement(i === 0 ? 'strong' : 'div');
    p.textContent = l;
    div.append(p);
  });
  return div;
}
