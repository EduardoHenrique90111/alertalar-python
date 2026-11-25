# Base oficial embutida: `atlas-desastres-chuva.csv.gz`

Histórico oficial de desastres ligados a chuva de todos os municípios brasileiros, carregado no
banco uma única vez pela migração `V4__historico_oficial_atlas` (em `alertalar/migracoes`).

## Origem

- **Fonte:** Atlas Digital de Desastres no Brasil, versão 1.1, publicada em 06/08/2026 pelo
  Ministério da Integração e do Desenvolvimento Regional (MIDR), Secretaria Nacional de Defesa
  Civil (Sedec). Consolida os registros do S2iD (Sistema Integrado de Informações sobre Desastres).
- **Página:** https://atlasdigital.mdr.gov.br
- **Arquivo original:** `BD_Atlas_1991_2025_v1.1_2026.08.06_Consolidado.csv` (86.134.318 bytes,
  Windows-1252, separado por `;`, 70 colunas; SHA-256
  `78f7efd2d853021678ff4af891e938375b9fd0ce77026cbe052a53dae12bf425`).

## Filtro e transformação

Gerado com `python -m alertalar.ferramentas.preparar_base_atlas`:

- 76.190 registros lidos no arquivo original;
- mantidos os de tipologia **Inundações** (COBRADE 1.2.1), **Enxurradas** (1.2.2),
  **Alagamentos** (1.2.3) e **Chuvas Intensas** (1.3.2.1.4): 27.581 registros, de 21/01/1991 a
  31/12/2025, nenhum descartado por dado inválido;
  - Enxurradas: 9.854; Chuvas Intensas: 9.153; Inundações: 6.430; Alagamentos: 2.144;
- colunas mantidas: protocolo do S2iD, UF, município, código IBGE, data do evento, COBRADE,
  tipologia, status (Registro ou Reconhecido) e danos informados (mortos, desabrigados,
  desalojados, casas danificadas e destruídas);
- saída em UTF-8, ordenada por código IBGE, data e protocolo, compactada com gzip.

As chuvas intensas entram porque muitas enchentes são registradas com esse tipo (as de maio de
2024 em Canoas e Porto Alegre, por exemplo).

## Limites

- São registros **municipais**: indicam que a cidade foi afetada, não qual rua.
- A data usada é a coluna `Data_Evento` do Atlas. Em parte dos registros antigos ela coincide com
  a data de registro no S2iD; o final do protocolo (AAAAMMDD) traz a data informada pelo município
  e ajuda a conferir.
- Dependem de a prefeitura ter registrado o evento no S2iD. A ausência de registro não prova que
  o município nunca teve enchente.
- Eventos de 2026 em diante entram importando uma planilha mais nova pela tela de Moderação
  (registros repetidos são ignorados pelo protocolo) ou regenerando este arquivo com uma versão
  mais nova do Atlas e uma nova migração.

# Lista de municípios: `municipios-ibge.csv.gz`

Código IBGE, UF e cada grafia do nome de município que aparece no mesmo arquivo do Atlas (todas as
tipologias de desastre): 5.307 linhas para 5.256 municípios. Usada por `MunicipiosIbge`
(`alertalar/integracoes/ibge.py`) para
achar o código IBGE sem depender da API do IBGE. Os cerca de 300 municípios fora da lista não têm
nenhum registro no Atlas; para eles o sistema ainda consulta a API do IBGE.

Gerada pela mesma ferramenta, com um terceiro argumento:

```bash
python -m alertalar.ferramentas.preparar_base_atlas \
  BD_Atlas_1991_2025_v1.1_2026.08.06_Consolidado.csv \
  alertalar/dados/atlas-desastres-chuva.csv.gz \
  alertalar/dados/municipios-ibge.csv.gz
```
