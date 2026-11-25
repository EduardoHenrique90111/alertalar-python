// Página de resultado: régua de risco, mapa com dados reais, fatores, histórico e situação atual.
/* global L */
import { api } from '../api.js';
import { data, dataHora, el, iniciarCabecalho, limpar, mensagem, metros, numero } from '../ui.js';
import { criarMapa, icone, popup } from '../mapa.js';

iniciarCabecalho();

const id = new URLSearchParams(location.search).get('id');
const $ = (s) => document.getElementById(s);

const ROTULO_CATEGORIA = { RISCO_MAPEADO: 'Risco mapeado', SUSCETIBILIDADE: 'Suscetibilidade', HISTORICO: 'Histórico' };
const ROTULO_TIPO_FONTE = { API_EXTERNA: 'Serviço externo', BASE_GEOGRAFICA: 'Base geográfica', IMPORTACAO_OFICIAL: 'Registro oficial importado', RELATO_USUARIO: 'Relatos verificados' };

async function carregar() {
  if (!id || !/^[0-9a-f-]{36}$/i.test(id)) {
    erro('O endereço desta página não contém uma consulta válida.');
    return;
  }
  try {
    const r = await api('/api/consultas/' + encodeURIComponent(id));
    renderizar(r);
    carregarSituacao(r.endereco.latitude, r.endereco.longitude, r.id);
  } catch (e) {
    erro(e.status === 404 ? 'Esta consulta não existe ou o link está incompleto.' : e.message);
  }
}

function erro(texto) {
  $('r-carregando').classList.add('oculto');
  const caixa = $('r-erro');
  mensagem(caixa, 'erro', texto, 'Não foi possível abrir o resultado');
  caixa.append(el('p', {}, el('a', { class: 'botao', href: '/#consultar' }, 'Fazer uma nova consulta')));
}

function renderizar(r) {
  document.title = r.endereco.descricao + ' | AlertaLar';
  $('r-endereco').textContent = r.endereco.descricao;
  $('r-meta').textContent = 'Consultado em ' + dataHora(r.dataConsulta) + '. Posição: ' + r.endereco.descricaoPrecisao.toLowerCase() + '.';
  const avisos = $('r-avisos');
  r.avisos.forEach((a, i) => {
    // o aviso de precisão (quando existe) vem primeiro e merece destaque; os demais são notas
    if (i === 0 && r.endereco.precisao === 'RUA') avisos.append(el('div', { class: 'mensagem mensagem-atencao' }, el('p', {}, a)));
    else avisos.append(el('p', { class: 'dica' }, a));
  });

  // Régua: o nível da água sobe até o índice (0 a 100)
  const regua = $('r-regua');
  const nivel = r.classificacao;
  const indice = r.indice ?? 0;
  regua.dataset.nivel = nivel;
  regua.setAttribute('aria-label', `Régua de risco: ${r.rotulo}` + (r.indice !== null ? `, índice ${numero(r.indice)} de 100` : ', sem leitura'));
  if (r.indice === null) $('r-marca').classList.add('oculto');
  requestAnimationFrame(() => requestAnimationFrame(() => {
    $('r-agua').style.height = indice + '%';
    $('r-marca').style.bottom = indice + '%';
  }));
  const rotulo = $('r-rotulo');
  rotulo.dataset.nivel = nivel;
  rotulo.textContent = r.rotulo;
  $('r-resumo').textContent = capitalizar(r.resumo.includes(': ') ? r.resumo.substring(r.resumo.indexOf(': ') + 2) : r.resumo);
  const ind = $('r-indice');
  if (r.indice !== null) {
    ind.append('Índice ' + numero(r.indice) + ' de 100',
      el('small', {}, 'Média ponderada dos fatores avaliados. Não é uma probabilidade de enchente.'));
  } else {
    ind.append(el('small', {}, 'Sem índice: não houve dados suficientes para calcular.'));
  }

  renderizarDimensoes(r.dimensoes);
  renderizarFatores(r.fatores);
  renderizarOcorrencias(r.ocorrenciasProximas, r.mapa);
  renderizarHistorico(r.historicoMunicipal);
  renderizarFontes(r.fontes);
  $('r-justificativa').textContent = r.justificativa;

  const rel = new URLSearchParams({ lat: r.endereco.latitude, lon: r.endereco.longitude, municipio: r.endereco.cidade, estado: r.endereco.estado });
  $('link-relatar').href = '/relatar.html?' + rel.toString();
  $('link-rota').href = '/rota.html?' + new URLSearchParams({ lat: r.endereco.latitude, lon: r.endereco.longitude }).toString();
  $('botao-copiar').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      mensagem($('msg-copiar'), 'sucesso', 'Link copiado. Quem tiver o link poderá ver este resultado.');
    } catch {
      mensagem($('msg-copiar'), 'atencao', 'Não foi possível copiar automaticamente. Copie o endereço da barra do navegador.');
    }
  });

  $('r-carregando').classList.add('oculto');
  $('resultado').classList.remove('oculto');
  renderizarMapa(r);
}

function renderizarDimensoes(dimensoes) {
  const c = $('r-dimensoes');
  dimensoes.forEach((d) => c.append(
    el('div', { class: 'dim', dataset: { nivel: d.nivel } },
      el('h3', {}, d.titulo),
      el('span', { class: 'nivel' }, d.rotuloNivel),
      el('p', {}, d.descricao))));
}

function renderizarFatores(fatores) {
  const lista = $('r-fatores');
  fatores.forEach((f) => {
    const avaliado = f.situacao === 'AVALIADO';
    const legenda = avaliado ? 'de 3 pontos' : f.situacao === 'SEM_REGISTRO' ? 'sem registro' : 'indisponível';
    const pontos = el('div', { class: 'fator-pontos', dataset: { p: avaliado ? String(f.pontuacao) : '' }, 'aria-hidden': 'true' },
      avaliado ? String(f.pontuacao) : '–',
      el('small', {}, legenda),
      el('span', { class: 'barras' }, el('i'), el('i'), el('i')));
    const selo = f.situacao === 'INDISPONIVEL' ? el('span', { class: 'selo selo-indisponivel' }, 'Fonte indisponível')
      : f.situacao === 'SEM_REGISTRO' ? el('span', { class: 'selo selo-sem-registro' }, 'Sem registro: não pontua')
        : el('span', { class: 'selo' }, ROTULO_CATEGORIA[f.categoria]);
    const meta = [];
    if (f.fonteNome) meta.push('Fonte: ' + f.fonteNome + '.');
    if (f.dataReferencia) meta.push('Dados obtidos em ' + dataHora(f.dataReferencia) + '.');
    meta.push('Peso ' + String(f.peso).replace('.', ',') + '.');
    lista.append(el('li', { class: 'fator' },
      pontos,
      el('div', {},
        el('h3', {}, f.nome, selo),
        el('span', { class: 'sr' }, avaliado ? `Pontuação ${f.pontuacao} de 3.` : legenda),
        f.valorObservado ? el('p', { class: 'valor' }, f.valorObservado) : null,
        el('p', {}, f.explicacao),
        el('p', { class: 'meta-fator' }, meta.join(' ')))));
  });
}

function itemOcorrencia(o) {
  return el('li', { class: o.origem === 'OFICIAL' ? 'oficial' : '' },
    el('span', { class: 'data' }, data(o.dataOcorrencia)),
    el('span', { class: 'selo ' + (o.origem === 'OFICIAL' ? 'selo-oficial' : 'selo-relato') }, o.origemRotulo),
    el('span', { class: 'selo' }, o.tipoEventoRotulo),
    el('p', {}, o.localizacao + (o.distanciaMetros !== null ? ` (a ${metros(o.distanciaMetros)})` : '')),
    el('p', { class: 'texto-secundario' }, o.descricao));
}

function renderizarOcorrencias(lista, mapa) {
  const c = $('r-ocorrencias');
  const raio = mapa && mapa.raios ? mapa.raios.ocorrencias : 500;
  if (!lista.length) {
    c.append(el('p', { class: 'vazio' }, `Nenhuma ocorrência confirmada com localização num raio de ${metros(raio)}.`),
      el('p', { class: 'dica' }, 'Isso não indica ausência de risco: a base depende de registros oficiais com localização e de relatos verificados.'));
    return;
  }
  c.append(el('p', { class: 'texto-secundario' }, `${lista.length} ocorrência(s) confirmada(s) num raio de ${metros(raio)}.`),
    el('ul', { class: 'lista-ocorrencias' }, lista.slice(0, 20).map(itemOcorrencia)));
}

function renderizarHistorico(h) {
  const c = $('r-historico');
  if (h.municipioIdentificado === false) {
    c.append(el('p', { class: 'vazio' }, 'Não foi possível identificar o município deste endereço, então o histórico oficial não foi consultado. Confira o nome da cidade e faça uma nova consulta.'));
    return;
  }
  if (!h.baseImportada) {
    c.append(el('p', { class: 'vazio' }, 'Não há registros oficiais do Atlas Digital/S2iD carregados para este estado no AlertaLar.'));
    return;
  }
  if (h.total === 0) {
    c.append(el('p', {}, 'Não constam registros oficiais de inundação, enxurrada, alagamento ou chuvas intensas para o município nos últimos 30 anos. Isso não significa que nunca houve enchente: depende de a prefeitura ter registrado o evento.'));
    return;
  }
  c.append(el('p', { class: 'texto-secundario' }, `${h.total} registro(s) oficial(is) no município nos últimos 30 anos. São registros municipais: não indicam que este endereço foi atingido.`),
    el('ul', { class: 'lista-ocorrencias' }, h.registros.map((o) => el('li', { class: 'oficial' },
      el('span', { class: 'data' }, data(o.dataOcorrencia)),
      el('span', { class: 'selo' }, o.tipoEventoRotulo),
      el('p', { class: 'texto-secundario' }, o.descricao)))));
}

function renderizarFontes(fontes) {
  const tbody = $('r-fontes');
  fontes.forEach((f) => tbody.append(el('tr', {},
    el('td', {}, f.url ? el('a', { href: f.url, rel: 'noopener', target: '_blank' }, f.nome) : f.nome),
    el('td', {}, ROTULO_TIPO_FONTE[f.tipo] || f.tipo),
    el('td', {}, f.dataAtualizacao ? dataHora(f.dataAtualizacao) : 'Sem registro'),
    el('td', {}, f.descricao || ''))));
}

function renderizarMapa(r) {
  const lat = r.endereco.latitude;
  const lon = r.endereco.longitude;
  const mapa = criarMapa($('r-mapa'), { centro: [lat, lon], zoom: 16 });
  const m = r.mapa || {};

  (m.cursosDagua || []).forEach((c) => {
    c.linhas.forEach((linha) => {
      const opcoes = { color: '#2f7fb8', weight: c.principal ? 5 : 3, opacity: 0.85 };
      const forma = c.area && linha.length > 3
        ? L.polygon(linha, { ...opcoes, weight: 2, fillColor: '#2f7fb8', fillOpacity: 0.25 })
        : L.polyline(linha, opcoes);
      forma.bindPopup(popup(capitalizar(c.descricao), 'Distância: ' + metros(c.distanciaMetros), 'Fonte: OpenStreetMap')).addTo(mapa);
    });
  });
  if (m.aguaMaisProxima) {
    L.polyline([[lat, lon], [m.aguaMaisProxima.lat, m.aguaMaisProxima.lon]], { color: '#12355b', weight: 2, dashArray: '6 6' })
      .bindTooltip(metros(m.aguaMaisProxima.distanciaMetros) + ' até ' + m.aguaMaisProxima.descricao, { sticky: true })
      .addTo(mapa);
  }
  (m.setoresRisco || []).filter((s) => s.hidrologico).forEach((s) => {
    s.aneis.forEach((anel) => L.polygon(anel, { color: '#c8372d', weight: 2, fillColor: '#c8372d', fillOpacity: 0.22 })
      .bindPopup(popup('Setor de risco ' + (s.numero || ''), s.grau ? 'Grau: ' + s.grau : null, s.tipologia, s.local,
        s.anoSetorizacao ? 'Mapeado em ' + s.anoSetorizacao : null, 'Fonte: Serviço Geológico do Brasil'))
      .addTo(mapa));
  });
  if (m.raios) {
    L.circle([lat, lon], { radius: m.raios.ocorrencias, color: '#12355b', weight: 1, dashArray: '4 6', fill: false, interactive: false }).addTo(mapa);
  }
  r.ocorrenciasProximas.filter((o) => o.latitude !== null).forEach((o) => {
    L.marker([o.latitude, o.longitude], { icon: icone(o.origem === 'OFICIAL' ? 'oficial' : 'relato'), title: o.tipoEventoRotulo })
      .bindPopup(popup(o.tipoEventoRotulo + ' em ' + data(o.dataOcorrencia), o.origemRotulo, o.localizacao))
      .addTo(mapa);
  });
  L.marker([lat, lon], { icon: icone('imovel'), title: 'Imóvel consultado', zIndexOffset: 1000 })
    .bindPopup(popup('Imóvel consultado', r.endereco.descricao)).addTo(mapa);
}

async function carregarSituacao(lat, lon, consulta) {
  const c = $('r-situacao');
  try {
    const s = await api('/api/situacao-atual', { params: { lat, lon, consulta } });
    renderizarAgora(s.riscoAgora, s.consultadoEm);
    limpar(c);
    if (s.chuva.disponivel) {
      c.append(el('h3', {}, 'Chuva no ponto'),
        el('div', { class: 'medidas' },
          medida(s.chuva.ultimas24hMm, 'mm nas últimas 24 horas'),
          medida(s.chuva.ultimas72hMm, 'mm nas últimas 72 horas'),
          medida(s.chuva.proximas24hMm, 'mm previstos nas próximas 24 horas'),
          medida(s.chuva.proximas72hMm, 'mm previstos em 3 dias'),
          medida(Math.max(s.chuva.maiorIntensidadeHorariaUltimas24hMm ?? 0, s.chuva.maiorIntensidadeHorariaProximas24hMm ?? 0), 'mm na hora mais chuvosa (24 h antes e depois)')),
        el('p', { class: 'dica' }, 'Fonte: ' + s.chuva.fonte + '. ' + s.riscoAgora.criterio));
    } else {
      c.append(el('p', { class: 'vazio' }, 'Dados de chuva indisponíveis agora: ' + s.chuva.motivo));
    }
    if (s.vazao.disponivel) {
      const tendencia = { SUBINDO: 'tendência de alta nos próximos dias', DESCENDO: 'tendência de baixa', ESTAVEL: 'estável' }[s.vazao.tendencia] || '';
      c.append(el('h3', {}, 'Rio mais próximo na grade do modelo'),
        el('div', { class: 'medidas' },
          medida(s.vazao.hojeM3s, 'm³/s hoje' + (tendencia ? ', ' + tendencia : '')),
          s.vazao.seteDiasAtrasM3s !== null ? medida(s.vazao.seteDiasAtrasM3s, 'm³/s há 7 dias') : null,
          s.vazao.maximaPrevista7DiasM3s !== null ? medida(s.vazao.maximaPrevista7DiasM3s, 'm³/s, máxima prevista em 7 dias') : null),
        el('p', { class: 'dica' }, s.vazao.observacao + ' Fonte: ' + s.vazao.fonte + '.'));
    } else {
      c.append(el('p', { class: 'vazio' }, 'Vazão de rios: ' + s.vazao.motivo));
    }
    c.append(el('ul', {}, s.avisos.map((a) => el('li', {}, a))));
  } catch (e) {
    renderizarAgora({ nivel: 'INDISPONIVEL', rotulo: 'Indisponível', resumo: 'Não foi possível consultar a chuva agora: ' + e.message, motivos: [] });
    limpar(c);
    c.append(el('p', { class: 'vazio' }, 'Não foi possível consultar a situação atual: ' + e.message));
  }
}

// Risco agora: chuva do momento combinada com a suscetibilidade do local
function renderizarAgora(r, consultadoEm) {
  $('r-agora').dataset.nivel = r.nivel;
  $('r-agora-rotulo').textContent = r.rotulo;
  $('r-agora-resumo').textContent = r.resumo + (consultadoEm ? ' Atualizado às ' + dataHora(consultadoEm).split(', ').pop() + '.' : '');
  const lista = limpar($('r-agora-motivos'));
  (r.motivos || []).forEach((m) => lista.append(el('li', {}, m)));
  if (r.proximosDias) lista.append(el('li', {}, el('strong', {}, r.proximosDias)));
}

function medida(valor, rotulo) {
  return el('div', { class: 'medida' }, el('strong', {}, numero(valor)), el('span', {}, rotulo));
}

function capitalizar(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

carregar();
