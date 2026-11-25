# Arquitetura do AlertaLar

## Visão geral

```
Navegador (HTML + CSS + JavaScript puro + Leaflet)
        │  fetch JSON, mesma origem, cookie de sessão + token CSRF
        ▼
FastAPI + Uvicorn (Python 3.12+)
  controladores  →  servicos  →  repositorios  →  PostgreSQL (SQLAlchemy + migrações)
                      │
                      ├── servicos/analise  (fatores de risco independentes + consolidação)
                      └── integracoes       (clientes HTTP das fontes externas)
```

O próprio servidor entrega o front-end (pasta `frontend/`), então tudo roda em
`http://localhost:8080` sem configuração de CORS. A API e o front-end são os mesmos da versão
em Java: as mesmas rotas, o mesmo JSON (nomes em camelCase) e os mesmos erros.

## Camadas (pacote `alertalar`)

| Módulo | Responsabilidade |
|---|---|
| `aplicacao.py` | Cria a aplicação FastAPI: rotas da API, site estático, `/actuator/health`, migrações e administrador inicial ao ligar. `__main__.py` sobe o Uvicorn (`python -m alertalar`). |
| `container.py` | Monta os serviços e os clientes externos uma vez (injeção de dependências simples). |
| `config.py` | Lê as variáveis de ambiente e o `.env`; converte a connection string do Neon (`DATABASE_URL`). |
| `controladores/` | Endpoints REST, leitura e validação da entrada, usuário logado. |
| `servicos/` | Regras de negócio: geocodificação (`GeocodificacaoService`, `EnderecoService`), orquestração da consulta (`ConsultaService`), coleta de dados em paralelo (`ColetaDadosService`), rota segura (`RotaSeguraService`), ocorrências e moderação, importação oficial, situação atual, usuários. |
| `servicos/analise/` | Metodologia de risco: `FatorRisco` (classe base), um fator por classe em `fatores.py`, `AnaliseRiscoService` (consolidação) e `risco_agora.py` (nível da chuva e risco agora). |
| `repositorios.py` | Acesso ao banco com SQLAlchemy (consultas parametrizadas). |
| `modelos/` | Tabelas (SQLAlchemy ORM) e enums. |
| `esquemas.py` | Entrada e saída da API (modelos pydantic) com as mesmas mensagens de validação. |
| `integracoes/` | Clientes de ViaCEP, Nominatim, Photon, IBGE, Overpass, Open-Meteo, SGB, Valhalla (rotas) e leitor de CSV do S2iD. `ClienteHttpExterno` (em `http.py`) centraliza tempo limite, User-Agent e tratamento de falhas. |
| `seguranca.py` | Sessão, CSRF, permissões, limitador de requisições, CORS e cabeçalhos de segurança (um middleware ASGI). |
| `migracoes/` | Estrutura do banco, aplicada ao ligar: `V1`, `V2`, `V3` e `V5` em SQL e `V4` em Python (carga da base oficial do Atlas Digital). |
| `dados/` | Base oficial embutida (`atlas-desastres-chuva.csv.gz`) e lista de municípios do IBGE. |
| `ferramentas/` | Utilitário de linha de comando que gera a base compacta do Atlas Digital (`preparar_base_atlas`); não roda com a aplicação. |
| `erros.py` | Exceções de negócio e respostas de erro no formato Problem Details (RFC 9457). |
| `util/` | Texto, números (arredondamento e formato brasileiro), UFs e cálculos geográficos. |

## Fluxo de uma consulta

1. O usuário informa o endereço; o CEP preenche o formulário (ViaCEP).
2. `GET /api/enderecos/buscar` geocodifica e devolve candidatos com a precisão
   (`NUMERO`, `RUA` ou aproximada). O usuário confirma ou ajusta a posição no mapa.
   `GeocodificacaoService` tenta o Nominatim (estruturado, texto livre, nome junto); se ele
   recusar (429/403), falhar ou não achar, tenta o Photon. Uma recusa põe o Nominatim em pausa
   (o tempo do `Retry-After`, entre 1 e 30 min; 5 min sem ele; 30 min para 403; 1 min para
   falhas passageiras), e nesse tempo o Photon vem primeiro. Resultado do Photon cujo nome não
   bate com o digitado vale só como posição aproximada. Endereços encontrados ficam 24 h em
   memória. Se nenhum dos dois responder, a API devolve 503 e a tela oferece marcar no mapa.
3. `POST /api/consultas`:
   - `EnderecoService` resolve o ponto (precisão mínima: rua; ou posição confirmada no mapa);
   - `ColetaDadosService` consulta em paralelo (um conjunto de threads) Overpass e SGB, e a
     elevação logo depois dos rios; lê do banco as ocorrências confirmadas e o histórico
     municipal. Cada fonte que falha vira "indisponível" sem derrubar as outras;
   - cada `FatorRisco` avalia o contexto; `AnaliseRiscoService` consolida;
   - a consulta, os fatores e as geometrias exibidas no mapa são gravados.
4. `GET /api/consultas/{id}` reabre o resultado; a página chama
   `GET /api/situacao-atual?consulta={id}`, que mede a chuva e a vazão (15 min em cache por grade
   de ~1 km) e calcula o **risco agora** (`risco_agora.avaliar`): nível da chuva pelos limites
   do INMET combinado com a classificação gravada da consulta. A classificação não muda.

O código IBGE do município (para o histórico oficial) vem do ViaCEP, da lista local
`MunicipiosIbge` ou da API do IBGE, nessa ordem; endereços guardados sem código são completados
na consulta seguinte.

## Fluxo da rota segura

`GET /api/rotas/segura?lat=&lon=&destLat=&destLon=&modo=` (`RotaSeguraService`). O destino é
sempre escolhido pela pessoa (endereço, nome do local ou ponto no mapa), até 20 km da partida.

1. Em paralelo, pede a altura da partida e do destino (Open-Meteo/Copernicus) e os setores de
   risco do SGB num raio de metade da distância mais 1,5 km em volta do trajeto (só os
   hidrológicos são usados). Avisa se a partida ou o destino estão dentro de um setor, ou se o
   destino é mais de 2 m mais baixo que a partida.
2. Pede o caminho ao Valhalla com os setores entre a partida e o destino em
   `exclude_polygons` (até 9 km de perímetro somado, os mais próximos do trajeto primeiro).
   Se não houver caminho com desvio, tenta sem desvio e avisa.
3. Confere o caminho: setores atravessados e perfil de altura em 60 pontos (aviso quando algum
   trecho fica mais de 2 m abaixo da partida, ou quando a altura não pôde ser consultada).
   O resultado fica 15 min em cache.

### Andamento em tempo real

`GET /api/rotas/segura/progresso` faz o mesmo cálculo e envia, por Server-Sent Events
(`StreamingResponse` com `text/event-stream`), um evento `etapa` a cada consulta externa que
começa, termina ou falha (`ProgressoRota`): primeiro o plano com as 4 etapas pendentes (ALTURA,
SETORES, CAMINHO, PERFIL), depois `EM_ANDAMENTO`, `CONCLUIDA` ou `FALHOU`, com o nome do serviço
consultado e um detalhe ("desviando de 2 áreas de risco", "1,2 km pelas ruas"). O último evento
é `resultado` (a mesma `RotaSeguraResponse`) ou `erro` (`{status, title, detail}`). Parâmetros
inválidos são recusados antes do andamento, com a resposta de erro comum. O cálculo roda numa
thread separada, que passa os eventos para a resposta por uma fila do `asyncio`, e tem até
3 minutos; se a pessoa cancelar ou fechar a página, a resposta é encerrada e o serviço para antes
da próxima chamada ao Valhalla ou ao Open-Meteo (nada vai para o cache).

No front-end, `js/progresso.js` desenha o painel sobre o mapa e `apiComAndamento` (em
`js/api.js`) lê os eventos com `fetch` e `ReadableStream`, o que permite cancelar com
`AbortController`. O painel também mostra as etapas do próprio navegador: GPS, busca do
endereço (Nominatim) e a espera pelo servidor, que no plano gratuito do Render pode levar cerca
de 1 minuto para acordar. Cada etapa tem um tempo a partir do qual aparece o aviso de demora.

## Metodologia (versão 1.0)

| Fator | Categoria | Peso | Pontuação (0–3) |
|---|---|---|---|
| Setor de risco SGB | Risco mapeado | 3 | dentro de setor alto/muito alto: 3 (força alto risco); setor ≤100 m: 2; ≤300 m: 1; nenhum: não pontua |
| Proximidade de água | Suscetibilidade | 2 | rio/canal/corpo d'água ≤150 m: 3, ≤400 m: 2, ≤1.000 m: 1; córrego/vala ≤50 m: 2, ≤150 m: 1; nada em 1.500 m: 0 |
| Elevação relativa | Suscetibilidade | 2 | desnível até a água ≤2 m: 3, ≤5 m: 2, ≤10 m: 1; ponto ≥5 m abaixo do entorno: 2, ≥2 m: 1 |
| Ocorrências próximas | Histórico | 2 | confirmadas em 500 m/30 anos: 1, 2, ≥3 (≥3 impede "baixo"); nenhuma: não pontua |
| Histórico municipal | Histórico | 0,75 | desastres oficiais ligados a chuva (inundação, enxurrada, alagamento, chuvas intensas) em 30 anos: 1–4: 1; ≥5: 2; base carregada sem registros: 0; sem base para a UF: não pontua |

Média ponderada M dos fatores avaliados: M ≥ 1,9 → alto; M ≥ 1,0 → moderado; abaixo → baixo.
Exige pelo menos dois fatores avaliados, um deles geográfico; senão, "dados insuficientes".
A ausência de dados nunca é tratada como evidência de segurança.

## Banco de dados e migrações

`alertalar/migracoes` aplica, ao ligar, as versões que ainda não estão na tabela
`historico_migracoes`, cada uma numa transação e com uma trava do PostgreSQL
(`pg_advisory_xact_lock`) para que duas instâncias não migrem ao mesmo tempo. Num banco criado
pela versão em Java, as versões já registradas pelo Flyway (`flyway_schema_history`) são
reconhecidas e não rodam de novo: as duas versões podem usar o mesmo banco.

As senhas usam o mesmo formato BCrypt da versão em Java (`$2a$`), então as contas existentes
continuam entrando.

## Segurança

- Sessão no servidor com cookie `ALERTALAR_SESSAO` `HttpOnly` + `SameSite=Lax` (expira após
  60 minutos sem uso) e proteção CSRF (`XSRF-TOKEN` em cookie, enviado no cabeçalho
  `X-XSRF-TOKEN`; o token muda ao entrar).
- Senhas com BCrypt (fator 12); a resposta da API nunca inclui o hash.
- `/api/admin/**` restrito ao papel `ADMIN`; o primeiro administrador vem de variáveis de ambiente.
- Validação de todas as entradas e limpeza de caracteres de controle.
- Consultas SQLAlchemy parametrizadas (sem SQL concatenado).
- Limite de requisições por IP nas rotas que consomem APIs externas ou recebem formulários.
- Cabeçalhos: Content-Security-Policy sem scripts/estilos inline, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy` e, com HTTPS, `Strict-Transport-Security`.
- Erros em formato Problem Details sem stack trace; erro inesperado gera um código para suporte
  e o detalhe só vai para o log do servidor.
- O front-end insere textos vindos da API com `textContent` (nunca `innerHTML`), evitando XSS.
- Nome e contato de quem relata são visíveis apenas para administradores.
- Sessões e limites ficam em memória: rode um único processo (o padrão de `python -m alertalar`).
  Para várias instâncias, troque por um armazenamento compartilhado (por exemplo, Redis).
