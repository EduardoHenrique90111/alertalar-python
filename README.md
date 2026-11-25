# AlertaLar (Python)

Sistema web de consulta e análise de riscos de enchentes e alagamentos em imóveis e regiões.
Esta é a versão em **Python** (FastAPI) do AlertaLar: o mesmo site, a mesma API e o mesmo banco
da versão em Java.

A pessoa informa um endereço, confirma a posição no mapa e recebe duas respostas:

- **Risco agora** (baixo, atenção, alto ou muito alto): a chuva das últimas horas e a prevista
  para as próximas 24 horas, pelos limites de chuvas intensas do INMET, combinadas com a
  suscetibilidade do local e a subida de rios próximos. É recalculado cada vez que o resultado
  é aberto.
- **Suscetibilidade do local** (**baixo risco**, **risco moderado**, **alto risco** ou **dados
  insuficientes**): o quanto o endereço tende a ser atingido quando chove forte, com a explicação
  de cada fator, as fontes usadas e a data dos dados. Não muda com o tempo do dia.

A página **Rota segura** sugere um caminho a pé ou de carro, a partir da localização da pessoa
ou de um endereço, até um lugar que ela escolher (casa de parente, abrigo, ponto de apoio),
desviando das áreas de risco de inundação mapeadas.

## Objetivo

Ajudar moradores, compradores e inquilinos a saber se um endereço fica em região historicamente
afetada por enchentes ou geograficamente suscetível a alagamentos, sempre separando:

- **risco mapeado**: setores de risco oficiais do Serviço Geológico do Brasil;
- **suscetibilidade geográfica**: proximidade de rios e córregos e altura relativa do terreno;
- **risco histórico**: desastres oficiais do município (inundações, enxurradas, alagamentos e
  chuvas intensas registrados no S2iD, de 1991 a 2025, já incluídos) e relatos de moradores verificados;
- **situação atual**: chuva e vazão de rios estimadas por modelos, que formam o risco agora.

O sistema nunca afirma que um local está livre de enchentes e não inventa dados: quando uma
fonte não responde ou não cobre a região, o fator aparece como indisponível e não entra na conta.

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Back-end | Python 3.12+, FastAPI, Uvicorn, pydantic |
| Banco de dados | PostgreSQL, SQLAlchemy 2 + psycopg 3, migrações próprias (compatíveis com as do Flyway da versão em Java) |
| Front-end | HTML5, CSS3, JavaScript puro (módulos ES), Leaflet 1.9.4 + OpenStreetMap |
| Testes | pytest |
| Integrações | ViaCEP, Nominatim (OSM) com o Photon (OSM) de reserva, IBGE Localidades, Overpass (OSM), Open-Meteo (elevação Copernicus, chuva, vazão GloFAS), SGB (setores de risco), Valhalla (rotas sobre o OSM); base do Atlas Digital de Desastres embutida e importação de planilhas do S2iD |

Fontes tipográficas (Overpass e Public Sans, licença OFL) e Leaflet ficam dentro do projeto:
o front-end não depende de CDN.

## Requisitos

- **Python 3.12 ou superior** (testado com 3.13)
- **PostgreSQL 14+**
- Internet: para o `pip` baixar as dependências e para o sistema consultar as APIs públicas

## Instalação

### 1. PostgreSQL

Crie o usuário e o banco (uma vez):

```bash
psql -U postgres -f database/criar-banco.sql
```

Troque a senha `troque_esta_senha` no script antes de executar. As tabelas são criadas
automaticamente quando o servidor inicia.

Já tem o banco da versão em Java? Pode usar o mesmo: as tabelas criadas pelo Flyway são
reconhecidas e as senhas BCrypt continuam valendo.

### 2. Ambiente Python e dependências

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

(`requirements.txt` tem só o necessário para rodar; `requirements-dev.txt` acrescenta o pytest.)

### 3. Variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` (ele fica fora do Git):

| Variável | Para quê |
|---|---|
| `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` | Conexão com o PostgreSQL (`DB_URL=postgresql://localhost:5432/alertalar`; o formato `jdbc:postgresql://...` da versão em Java também é aceito) |
| `DATABASE_URL` | Alternativa às três acima: a connection string completa, como o Neon mostra |
| `ALERTALAR_ADMIN_EMAIL`, `ALERTALAR_ADMIN_SENHA` | Cria o administrador (moderação e importação). Senha com 10+ caracteres, letras e números |
| `ALERTALAR_CONTATO_EMAIL` | Contato enviado às APIs públicas (pedido pela política do Nominatim) |
| `ALERTALAR_URL_PUBLICA` | Endereço do site, enviado no User-Agent para as APIs públicas identificarem o AlertaLar. No Render é preenchido sozinho (`RENDER_EXTERNAL_URL`) |
| `PORT` | Porta HTTP (padrão 8080) |
| `DB_POOL` | Conexões abertas ao mesmo tempo com o banco (padrão 10; use 5 no plano gratuito do Neon) |
| `COOKIE_SECURE`, `FORWARD_HEADERS_STRATEGY` | Use `true` e `framework` quando publicar com HTTPS atrás de proxy |
| `ROTAS_URL`, `ROTAS_CHAVE_API` | Opcional. Servidor de rotas compatível com o Valhalla (padrão: servidor público da FOSSGIS, sem chave) |

O servidor lê o `.env` da pasta onde é iniciado (e da pasta acima dela). Variáveis de ambiente
do sistema operacional têm prioridade sobre ele.

### 4. APIs externas

Nenhuma chave é necessária: todas as integrações ativas usam serviços públicos gratuitos.
A rota segura usa o servidor público do Valhalla mantido pela FOSSGIS
(`valhalla1.openstreetmap.de`), que aceita no máximo uma requisição por segundo; o AlertaLar
respeita esse intervalo e limita cada visitante a 10 rotas por minuto. Para uso intenso, aponte
`ROTAS_URL` para uma instância própria ou um provedor compatível (com `ROTAS_CHAVE_API`).
A busca de endereços usa o Nominatim público. Ele limita os pedidos por IP, e em hospedagens
compartilhadas (como o plano gratuito do Render) esse limite pode ser atingido por outros sites
do mesmo IP: quando o Nominatim recusa (HTTP 429 ou 403) ou não responde, a busca segue na hora
no Photon (komoot), que usa os mesmos dados do OpenStreetMap, e o Nominatim fica alguns minutos
em pausa. Se os dois estiverem fora do ar, a tela oferece marcar a posição direto no mapa.
Os endereços podem ser trocados por variáveis (`NOMINATIM_URL`, `PHOTON_URL`, `OVERPASS_URL`
etc., veja o `.env.example`), por exemplo para usar uma instância própria do Nominatim. Detalhes, limites
de uso e situação de cada fonte: [docs/fontes-de-dados.md](docs/fontes-de-dados.md).

## Como iniciar

Na pasta do projeto, com o ambiente virtual ativo:

```bash
python -m alertalar
```

Abra **http://localhost:8080**. O mesmo servidor entrega a API e o site (pasta `frontend/`),
então não é preciso um servidor separado para o front-end; basta recarregar o navegador depois
de editar um arquivo do site.

**No PyCharm ou no IntelliJ IDEA (com o plugin Python):** abra a pasta do projeto, escolha o
interpretador do `.venv` e crie uma configuração de execução do tipo *Python* com *Module name*
`alertalar` e a pasta do projeto como *Working directory*.

### Primeiros passos

1. Consulte um endereço na página inicial. Na primeira inicialização, o servidor já carrega o
   histórico oficial de todos os municípios (veja abaixo); não é preciso importar nada.
2. Abra **Rota segura** para testar o caminho até um destino escolhido.
3. Entre com o administrador configurado no `.env` e abra **Moderação** para validar relatos.

### Histórico oficial embutido

O arquivo `alertalar/dados/atlas-desastres-chuva.csv.gz` traz 27.581 registros de desastres
ligados a chuva (inundações, enxurradas, alagamentos e chuvas intensas, de 1991 a 2025) de todos
os municípios, extraídos do **Atlas Digital de Desastres no Brasil v1.1** (MIDR/Sedec,
06/08/2026), que consolida os registros do S2iD. A migração `V4__historico_oficial_atlas`
grava esses registros no banco uma única vez.

As chuvas intensas (COBRADE 1.3.2.1.4) entram porque muitas enchentes são registradas com esse
tipo: as de maio de 2024 em Canoas e Porto Alegre, por exemplo.

Para incluir eventos mais novos, há dois caminhos:

- importar a planilha CSV do [S2iD](https://s2id.mi.gov.br) ou do
  [Atlas Digital](https://atlasdigital.mdr.gov.br) pela **Moderação** (registros repetidos são
  ignorados pelo número de protocolo);
- ou regenerar a base embutida a partir do CSV completo do Atlas e criar uma nova migração:

```bash
python -m alertalar.ferramentas.preparar_base_atlas \
  ~/Downloads/BD_Atlas_1991_2025_v1.1_2026.08.06_Consolidado.csv \
  alertalar/dados/atlas-desastres-chuva.csv.gz
```

Proveniência e filtro: [alertalar/dados/LEIA-ME.md](alertalar/dados/LEIA-ME.md).

## Testes

```bash
python -m pytest
```

Há 189 testes (pytest): validação de endereços, geocodificação (com a reserva do Photon quando
o Nominatim recusa pedidos), código IBGE, fatores e classificação de risco, risco agora (níveis
de chuva do INMET e combinação com a suscetibilidade), processamento da consulta, registro e
moderação de ocorrências, importação de planilhas, base oficial embutida, migrações (inclusive
sobre um banco criado pelo Flyway), rota segura (destino escolhido, desvio de áreas de risco,
perfil de altura, andamento em tempo real e cancelamento), tratamento de erros, segurança (com
senhas geradas pela versão em Java) e comunicação HTTP com as APIs externas (contra um servidor
local que responde no mesmo formato das APIs reais).

Os testes de **ponta a ponta** (`tests/test_integracao.py`) sobem a aplicação inteira com
PostgreSQL real e percorrem consulta, persistência, relato, moderação, importação, situação
atual, rota segura, cadastro e login. Eles e os testes de migração (18 no total) só rodam quando
existe a variável `ALERTALAR_TEST_DB_URL` apontando para um banco **exclusivo de testes** (os
dados dele são apagados):

```bash
# Linux/macOS
export ALERTALAR_TEST_DB_URL=postgresql://localhost:5432/alertalar_test
export ALERTALAR_TEST_DB_USERNAME=alertalar
export ALERTALAR_TEST_DB_PASSWORD=sua_senha
python -m pytest
```

```powershell
# Windows (PowerShell)
$env:ALERTALAR_TEST_DB_URL="postgresql://localhost:5432/alertalar_test"
$env:ALERTALAR_TEST_DB_USERNAME="alertalar"
$env:ALERTALAR_TEST_DB_PASSWORD="sua_senha"
python -m pytest
```

## Endpoints

Todas as respostas são JSON; erros seguem o formato Problem Details (RFC 9457), com mensagens
em português e, em erros de validação, o campo `erros` por campo. A descrição completa da API
(OpenAPI) fica em `/api/openapi.json`.

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| GET | `/api/enderecos/cep/{cep}` | público | Dados do CEP (ViaCEP) para preencher o formulário |
| GET | `/api/enderecos/buscar?rua=&numero=&bairro=&cidade=&estado=&cep=` | público | Valida e geocodifica; devolve candidatos e a precisão |
| POST | `/api/consultas` | público | Realiza a consulta de risco e grava o resultado (201) |
| GET | `/api/consultas/{id}` | público (link com UUID) | Resultado completo de uma consulta |
| GET | `/api/consultas/minhas` | logado | Histórico de consultas do usuário |
| GET | `/api/ocorrencias?estado=&municipio=&origem=&pagina=&tamanho=` | público | Ocorrências confirmadas (oficiais e relatos validados) |
| GET | `/api/ocorrencias/proximas?lat=&lon=&raio=&anos=` | público | Ocorrências confirmadas em torno de um ponto |
| POST | `/api/ocorrencias` | público | Envia relato (fica `PENDENTE`) |
| GET | `/api/fontes` | público | Fontes de dados, situação da integração e última atualização |
| GET | `/api/situacao-atual?lat=&lon=&consulta=` | público | Chuva (72 h passadas e 72 h previstas), vazão e risco agora; `consulta` (opcional, UUID) usa a suscetibilidade daquela consulta |
| GET | `/api/rotas/segura?lat=&lon=&destLat=&destLon=&modo=A_PE` | público | Caminho até o destino escolhido (`destLat`/`destLon` obrigatórios, até 20 km), desviando das áreas de risco (`modo`: `A_PE` ou `CARRO`; 10 por minuto por IP) |
| GET | `/api/rotas/segura/progresso?` (mesmos parâmetros) | público | A mesma rota, em `text/event-stream`: eventos `etapa` (altura da partida e do destino, áreas de risco, caminho, perfil, com a fonte consultada e o estado), depois `resultado` (a mesma resposta acima) ou `erro`. Usado pelo painel de andamento sobre o mapa; fechar a conexão interrompe o cálculo |
| POST | `/api/auth/registro` | público | Cria conta e já entra |
| POST | `/api/auth/login` | público | Entra (sessão) |
| POST | `/api/auth/logout` | logado | Sai |
| GET | `/api/auth/me` | público | Usuário logado (204 se ninguém) |
| GET | `/api/auth/csrf` | público | Gera o cookie `XSRF-TOKEN` |
| GET | `/api/admin/resumo` | ADMIN | Quantidade de relatos pendentes |
| GET | `/api/admin/ocorrencias?status=PENDENTE` | ADMIN | Relatos para moderação (inclui contato do relator) |
| PATCH | `/api/admin/ocorrencias/{id}/validacao` | ADMIN | Corpo `{"status":"CONFIRMADA","observacao":"..."}` (ou `REJEITADA`) |
| POST | `/api/admin/importacoes/registros-oficiais` | ADMIN | Upload `multipart/form-data` (campo `arquivo`, CSV do S2iD/Atlas) |
| GET | `/actuator/health` | público | Verificação de saúde (o mesmo caminho da versão em Java) |

Requisições `POST`/`PATCH` exigem o token CSRF: leia o cookie `XSRF-TOKEN` e envie no cabeçalho
`X-XSRF-TOKEN` (o front-end faz isso em `frontend/js/api.js`). Exemplo com curl:

```bash
curl -c c.txt -b c.txt http://localhost:8080/api/auth/csrf
TOKEN=$(grep XSRF-TOKEN c.txt | awk '{print $7}')
curl -c c.txt -b c.txt -X POST http://localhost:8080/api/consultas \
  -H "Content-Type: application/json" -H "X-XSRF-TOKEN: $TOKEN" \
  -d '{"rua":"Rua Exemplo","numero":"100","cidade":"Canoas","estado":"RS"}'
```

## Estrutura do projeto

```
alertalar-python/
├── alertalar/
│   ├── __main__.py          inicia o servidor (python -m alertalar)
│   ├── aplicacao.py         aplicação FastAPI: rotas, site estático, inicialização
│   ├── config.py            variáveis de ambiente e .env
│   ├── container.py         monta serviços e clientes externos
│   ├── seguranca.py         sessão, CSRF, permissões, limites, cabeçalhos
│   ├── controladores/       endpoints REST
│   ├── servicos/            regras de negócio
│   │   └── analise/         metodologia de risco (fatores independentes)
│   ├── repositorios.py      acesso ao banco (SQLAlchemy)
│   ├── modelos/             tabelas e enums
│   ├── esquemas.py          entrada e saída da API (pydantic)
│   ├── erros.py             exceções e respostas de erro (Problem Details)
│   ├── integracoes/         clientes das APIs externas e leitor do S2iD
│   ├── migracoes/           estrutura do banco (V1…V5)
│   ├── dados/               base oficial embutida e lista de municípios
│   ├── ferramentas/         preparo da base do Atlas Digital
│   └── util/                texto, números, UFs e geografia
├── frontend/
│   ├── index.html, resultado.html, ocorrencias.html, relatar.html,
│   │   entrar.html, painel.html, metodologia.html, rota.html
│   ├── css/estilo.css
│   ├── js/                  api.js, ui.js, mapa.js e scripts de cada página
│   └── assets/              fontes, ícone e Leaflet
├── tests/                   testes pytest (apoio/: servidor HTTP falso e respostas simuladas)
├── database/                script de criação do banco e modelo
├── docs/                    arquitetura, fontes de dados e publicação
├── Dockerfile, render.yaml, implantar-cloud-run.sh
├── requirements.txt, requirements-dev.txt, pyproject.toml
├── .env.example
└── README.md
```

## Publicação na internet

O GitHub guarda o código, mas não executa Python nem PostgreSQL. Dois caminhos gratuitos, os dois
com o banco no **Neon** (PostgreSQL):

- **Render**, sem cartão: o arquivo `render.yaml` cria o serviço (*New → Blueprint*) e só pede a
  connection string do Neon (`DATABASE_URL`). O site dorme após 15 minutos sem visitas e leva
  cerca de 1 minuto para acordar. Passo a passo: [docs/publicar-no-render.md](docs/publicar-no-render.md).
- **Google Cloud Run**, com cartão (sem cobrança dentro do nível gratuito): liga em segundos.
  Passo a passo: [docs/publicar-no-google-cloud.md](docs/publicar-no-google-cloud.md).

Variáveis usadas em produção:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | connection string do Neon (`postgresql://USUARIO:SENHA@HOST/BANCO?sslmode=require`), convertida sozinha para as três abaixo |
| `DB_URL` | `postgresql://HOST/BANCO?sslmode=require` (se definida, vale mais que `DATABASE_URL`) |
| `DB_USERNAME` / `DB_PASSWORD` | usuário e senha do banco |
| `DB_POOL` | `5` |
| `ALERTALAR_ADMIN_EMAIL` / `ALERTALAR_ADMIN_SENHA` | administrador (só para criar) |
| `ALERTALAR_CONTATO_EMAIL` | e-mail de contato para as APIs públicas |
| `COOKIE_SECURE` | `true` |
| `FORWARD_HEADERS_STRATEGY` | `framework` |

Observações:
- Rode **um processo só** (o padrão de `python -m alertalar` e do `Dockerfile`): sessões e o
  limitador de requisições ficam em memória. Com várias instâncias, use um armazenamento
  compartilhado.
- Com tráfego alto, troque o Nominatim e o Photon públicos e os blocos de mapa do OpenStreetMap por
  serviços próprios ou comerciais: as políticas de uso das instâncias públicas proíbem uso intenso.
- Para rodar em qualquer servidor: instale as dependências e rode `python -m alertalar` com
  Python 3.12+ e as mesmas variáveis (ou use o `Dockerfile`).

## Limitações conhecidas

- A classificação resume indícios nos dados disponíveis: não é laudo técnico, estudo
  hidrológico nem previsão meteorológica.
- Modelo de elevação de 90 m (Copernicus GLO-90): erro vertical de alguns metros e pode incluir
  construções e vegetação.
- O mapeamento de rios e córregos do OpenStreetMap varia por região; córregos canalizados podem
  não aparecer.
- O SGB mapeou setores de risco em parte dos municípios; a ausência de setor não é tratada como
  segurança.
- O risco agora usa chuva estimada por modelos (Open-Meteo), que erram a chuva de um bairro,
  principalmente em temporais isolados. Não é alerta oficial.
- O código IBGE do município vem do CEP (ViaCEP), de uma lista guardada no sistema (5.256
  municípios do Atlas Digital) ou da API do IBGE, nessa ordem. Se o nome da cidade estiver
  muito diferente do oficial, o histórico municipal fica indisponível.
- Registros do S2iD são municipais (não indicam a rua). A base embutida vai até 2025; eventos
  mais novos dependem de importar a planilha, pois não há API pública documentada. A importação
  aceita CSV (não XLSX). A ausência de registro não significa que o município nunca teve enchente.
- A rota segura não é rota oficial de evacuação: não sabe quais ruas estão alagadas ou
  bloqueadas, a altura do terreno tem erro de alguns metros e o desvio cobre só os setores
  mapeados pelo SGB. O servidor público de rotas pode recusar pedidos em horários de muito uso.
- CEMADEN, INMET e ANA ainda não estão integrados (acesso exige credencial ou não há API
  documentada); estão registrados como fontes planejadas.
- O índice da camada do SGB (`/MapServer/0`) segue o serviço público atual; se o SGB mudar o
  serviço, ajuste `SGB_SETORES_RISCO_URL`.
- Vazão do GloFAS tem resolução de ~5 km e pode não representar rios pequenos.
- O link de um resultado é público para quem o tiver (identificador UUID não sequencial).
