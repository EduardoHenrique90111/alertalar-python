# Fontes de dados do AlertaLar

Levantamento feito em novembro de 2026. A situação de cada fonte também fica registrada na
tabela `fonte_dados` e aparece em `GET /api/fontes` e na página "Como analisamos".

## Integradas (consultadas pelo sistema)

| Fonte | Uso no AlertaLar | Acesso | Condições de uso |
|---|---|---|---|
| **ViaCEP** (`viacep.com.br/ws/{cep}/json/`) | Preenche rua, bairro, cidade, UF e código IBGE a partir do CEP. Não fornece coordenadas, por isso o CEP sozinho nunca é usado na análise. | Gratuito, sem chave | Uso moderado; resultados em cache por 24 h. |
| **Nominatim / OpenStreetMap** (`nominatim.openstreetmap.org/search`) | Geocodificação (endereço → latitude/longitude) com nível de precisão. | Gratuito, sem chave | Política: no máximo 1 requisição/s, User-Agent identificável, cache obrigatório, sem geocodificação em massa, atribuição ao OSM. O AlertaLar impõe intervalo mínimo de 1,1 s, envia `AlertaLar/1.0 (+endereço do site; contato)`, guarda endereços na tabela `endereco` e, por 24 h, em memória. Quando ele recusa pedidos (429/403) ou não responde, fica alguns minutos em pausa e a busca segue no Photon. Para uso intenso, use uma instância própria ou um provedor comercial (configurável por `NOMINATIM_URL`). |
| **Photon (komoot)** (`photon.komoot.io/api`) | Reserva da geocodificação, com os mesmos dados do OpenStreetMap: usado quando o Nominatim recusa pedidos, não responde ou não acha o endereço. | Gratuito, sem chave | Uso justo ("número razoável de pedidos"; uso intenso é limitado ou bloqueado), sem garantia de disponibilidade. O AlertaLar busca só no Brasil (`bbox`), impõe intervalo mínimo de 1,1 s e trata como aproximado o resultado cujo nome não bate com o digitado, porque a busca do Photon tolera diferenças de escrita. Configurável por `PHOTON_URL`. |
| **IBGE – API de Localidades** (`servicodados.ibge.gov.br/api/v1/localidades`) | Código IBGE do município (cruzamento com registros oficiais), quando o CEP não informa e o município não está na lista guardada no sistema (`dados/municipios-ibge.csv.gz`, 5.256 municípios com código e grafias do nome, extraídos do Atlas Digital). | Gratuito, oficial | Cache por 24 h por UF. A lista local evita depender dessa API, que pode não responder a servidores fora do Brasil. |
| **Overpass API / OpenStreetMap** (`overpass-api.de/api/interpreter`) | Rios, córregos, canais, valas e corpos d'água num raio de 1.500 m, com geometria. | Gratuito | Uso justo (instância pública compartilhada); cache de 6 h por ponto. Dados ODbL, atribuição obrigatória. |
| **Copernicus DEM GLO-90 via Open-Meteo Elevation API** (`api.open-meteo.com/v1/elevation`) | Elevação do ponto, do curso d'água mais próximo e de 8 pontos do entorno (uma requisição). | Gratuito para uso não comercial; até 100 coordenadas por chamada | Atribuição ao programa Copernicus e à Open-Meteo. Uso comercial exige chave. |
| **Serviço Geológico do Brasil – Setorização de Riscos** (ArcGIS REST: `geoportal.sgb.gov.br/server/rest/services/gestaoterritorial/risco/MapServer/0/query`) | Setores de risco alto e muito alto; somente os hidrológicos (inundação, enxurrada, alagamento) pontuam. | Público, oficial | Campos usados: `uf`, `munic`, `num_setor`, `local`, `tipolo_g1..5`, `tipolo_e1..5`, `cobrade_01..05`, `descricao`, `grau_risco`, `data_setor`. O índice da camada (`/0`) é configurável por `SGB_SETORES_RISCO_URL`; se o SGB reorganizar o serviço, ajuste essa variável. O SGB mapeou apenas parte dos municípios. |
| **Open-Meteo Forecast API** (`api.open-meteo.com/v1/forecast`) | Risco agora: chuva horária das últimas 72 h e das próximas 72 h (`past_days=3`). | Gratuito para uso não comercial | Dados CC BY 4.0. Os níveis seguem os limites de avisos de chuvas intensas do INMET (veja a página "Como analisamos"). Não altera a suscetibilidade gravada na consulta. |
| **GloFAS via Open-Meteo Flood API** (`flood-api.open-meteo.com/v1/flood`) | Risco agora: vazão diária simulada do rio mais próximo (grade de ~5 km); previsão de subida de 50% ou mais perto de água leva a "atenção". | Gratuito para uso não comercial | Pode não representar rios pequenos. |
| **Valhalla / OpenStreetMap** (servidor público da FOSSGIS: `valhalla1.openstreetmap.de/route`) | Rota segura: caminho a pé (`pedestrian`) ou de carro (`auto`) até o destino escolhido, com os setores de risco hidrológico do SGB enviados em `exclude_polygons` e instruções em português. | Gratuito, sem chave | Política da FOSSGIS: no máximo 1 requisição/s, User-Agent identificável, uso moderado e atribuição ao OSM. O AlertaLar espera 1,1 s entre chamadas, limita 10 rotas por minuto por IP, guarda o resultado por 15 min e faz no máximo 4 chamadas por pedido. Para uso intenso, configure `ROTAS_URL` (instância própria ou provedor compatível, com `ROTAS_CHAVE_API`). O total de perímetro dos polígonos evitados é limitado a 9 km (o padrão do Valhalla é 10 km). |

## Base oficial embutida e importação (dados oficiais sem API documentada)

| Fonte | Como usar |
|---|---|
| **Atlas Digital de Desastres no Brasil v1.1** (MIDR/Sedec, 06/08/2026, registros do S2iD) | O sistema já vem com os 27.581 desastres ligados a chuva de todos os municípios de 1991 a 2025: inundações (COBRADE 1.2.1), enxurradas (1.2.2), alagamentos (1.2.3) e chuvas intensas (1.3.2.1.4). A migração `V4__historico_oficial_atlas` (em `alertalar/migracoes`) grava a base no primeiro início. Proveniência, filtro e soma de verificação do arquivo original: `alertalar/dados/LEIA-ME.md`. |
| **S2iD / Atlas Digital** (planilhas mais novas) | Não há API pública documentada. Para eventos posteriores à base embutida, o administrador baixa a planilha em `s2id.mi.gov.br` ou `atlasdigital.mdr.gov.br` e envia o CSV pela Moderação (`POST /api/admin/importacoes/registros-oficiais`). O leitor aceita UTF-8 ou Windows-1252, campos entre aspas com quebra de linha e variações de colunas (`UF`/`Sigla_UF`, `Município`/`Nome_Municipio`, `Cod_IBGE_Mun`, `Data do Evento`/`Data_Evento`/`Ano`, `COBRADE`/`Cod_Cobrade`/`Desastre`, `Protocolo`/`Protocolo_S2iD`). Registros repetidos são ignorados pelo protocolo. |

Os registros são municipais: mostram que a cidade foi atingida, não qual rua. A ausência de
registro não significa que o município nunca teve enchente, só que nada foi registrado no S2iD.

## Não integradas (estrutura preparada, sem simulação)

| Fonte | Motivo |
|---|---|
| **CEMADEN** | O acesso programático aos dados de pluviômetros exige cadastro/credencial. Foi encontrado um serviço ArcGIS no geoportal do SGB com estações do CEMADEN, mas ele está identificado como base de teste, por isso não foi usado. |
| **INMET** | Não foi encontrada documentação pública estável da API de avisos meteorológicos. |
| **ANA – HidroWebService** | Exige cadastro e credenciais (há manual público). Previsto para níveis de rios em tempo real. |

Para integrar uma delas: crie um cliente em `alertalar/integracoes/`, um fator em
`alertalar/servicos/analise/fatores.py` (incluído em `fatores_padrao()`) ou um bloco em
`SituacaoAtualService`, se for dado em tempo real, e altere o `status_integracao` da fonte com
uma nova migração (`V6__descricao.sql` em `alertalar/migracoes`).
