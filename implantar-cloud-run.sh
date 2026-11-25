#!/usr/bin/env bash
# =====================================================================
#  AlertaLar (Python) - publicação no Google Cloud Run
#
#  Rode no Cloud Shell (ícone >_ no topo do console do Google Cloud):
#      bash implantar-cloud-run.sh
#
#  O que este arquivo faz:
#   1. confere o projeto do Google Cloud e se o faturamento está ativo;
#   2. ativa os serviços necessários (Cloud Run, Cloud Build, Artifact Registry);
#   3. pede a "connection string" do banco no Neon (e dados opcionais);
#   4. compila o projeto pelo Dockerfile e publica no Cloud Run: desliga
#      sozinho quando ninguém usa e no máximo 2 cópias rodando ao mesmo tempo;
#   5. (opcional) cria um alerta por e-mail se houver qualquer gasto no mês.
#
#  Para publicar uma versão nova depois, rode de novo: dá para manter a
#  configuração atual do banco apertando Enter.
#  Detalhes: docs/publicar-no-google-cloud.md
# =====================================================================
set -euo pipefail

SERVICO="${SERVICO:-alertalar-python}"
cd "$(dirname "$0")"

titulo() { printf '\n\033[1;34m== %s ==\033[0m\n' "$1"; }
aviso() { printf '\033[1;33mAviso:\033[0m %s\n' "$1"; }
erro() { printf '\n\033[1;31mErro:\033[0m %s\n' "$1" >&2; exit 1; }

command -v gcloud >/dev/null 2>&1 \
  || erro "gcloud não encontrado. Rode este arquivo no Cloud Shell (ícone >_ no topo do console do Google Cloud)."
command -v python3 >/dev/null 2>&1 || erro "python3 não encontrado (o Cloud Shell já vem com ele)."
[ -f Dockerfile ] || erro "Dockerfile não encontrado. Entre na pasta do projeto (cd alertalar-python) antes de rodar."

# ---------------------------------------------------------------------
titulo "1/5 Projeto do Google Cloud"
PROJETO="$(gcloud config get-value project 2>/dev/null || true)"
if [ -z "$PROJETO" ] || [ "$PROJETO" = "(unset)" ]; then
  echo "Seus projetos:"
  gcloud projects list --format="table(projectId,name)"
  read -rp "Digite o ID do projeto (coluna PROJECT_ID): " PROJETO
  [ -n "$PROJETO" ] || erro "Nenhum projeto informado."
  gcloud config set project "$PROJETO" >/dev/null
fi
NUMERO="$(gcloud projects describe "$PROJETO" --format='value(projectNumber)')" \
  || erro "Não foi possível abrir o projeto $PROJETO."
echo "Projeto: $PROJETO"

gcloud services enable cloudbilling.googleapis.com --quiet >/dev/null 2>&1 || true
FATURAMENTO="$(gcloud billing projects describe "$PROJETO" --format='value(billingEnabled)' 2>/dev/null || true)"
case "${FATURAMENTO,,}" in
  true) echo "Faturamento ativo (dentro do nível gratuito do Cloud Run não há cobrança)." ;;
  false) erro "O projeto $PROJETO está sem conta de faturamento. No console, abra Faturamento (Billing),
vincule a conta de faturamento a este projeto e rode este arquivo de novo." ;;
  *) aviso "não consegui conferir o faturamento; se a publicação falhar, vincule uma conta de faturamento ao projeto." ;;
esac

# ---------------------------------------------------------------------
titulo "2/5 Ativando os serviços (pode levar 1 a 2 minutos)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --quiet
# Em projetos novos, a conta de serviço que compila o código precisa desta função
gcloud projects add-iam-policy-binding "$PROJETO" \
  --member="serviceAccount:${NUMERO}-compute@developer.gserviceaccount.com" \
  --role="roles/run.builder" --condition=None --quiet >/dev/null 2>&1 \
  || aviso "não foi possível dar a função 'Cloud Run Builder' à conta de serviço padrão. Se a compilação falhar por permissão, veja docs/publicar-no-google-cloud.md."
echo "Serviços ativos."

# ---------------------------------------------------------------------
titulo "3/5 Banco de dados e configuração"
REGIAO_ATUAL="$(gcloud run services list --filter="metadata.name=$SERVICO" \
  --format="value(metadata.labels.'cloud.googleapis.com/location')" 2>/dev/null | head -n1 || true)"
ARQ_ENV=""
REGIAO="${REGIAO:-}"
if [ -n "$REGIAO_ATUAL" ]; then
  echo "O serviço '$SERVICO' já existe na região $REGIAO_ATUAL."
  read -rp "Manter a configuração atual (banco, administrador)? [S/n] " MANTER
  REGIAO="${REGIAO:-$REGIAO_ATUAL}"
else
  MANTER="n"
fi

if [[ "${MANTER:-s}" =~ ^[Nn] ]]; then
  echo "No painel do Neon, clique em Connect e copie a connection string (começa com postgresql://)."
  read -rsp "Cole aqui (o texto não aparece na tela) e aperte Enter: " NEON
  echo
  read -rp "E-mail de contato enviado às APIs públicas, pedido pela política do OpenStreetMap (Enter para pular): " CONTATO
  read -rp "E-mail do administrador, só se quiser criar um novo (Enter para pular): " ADMIN_EMAIL
  ADMIN_SENHA=""
  if [ -n "$ADMIN_EMAIL" ]; then
    read -rsp "Senha do administrador (10+ caracteres, letras e números; não aparece na tela): " ADMIN_SENHA
    echo
  fi
  ARQ_ENV="$(mktemp)"
  chmod 600 "$ARQ_ENV"
  trap 'rm -f "$ARQ_ENV"' EXIT
  # Separa a connection string do Neon em endereço, usuário e senha e grava as variáveis (JSON)
  HOST_BANCO="$(NEON="$NEON" CONTATO="$CONTATO" ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_SENHA="$ADMIN_SENHA" \
    python3 - "$ARQ_ENV" <<'PY'
import json, os, sys, urllib.parse as up
texto = os.environ["NEON"].strip()
if texto.startswith("psql "):
    texto = texto[5:].strip()
texto = texto.strip("'\"")
p = up.urlparse(texto)
if p.scheme not in ("postgres", "postgresql") or not p.hostname or not p.username or p.password is None:
    sys.exit(2)
banco = up.unquote(p.path.lstrip("/")) or "neondb"
porta = f":{p.port}" if p.port else ""
env = {
    "DB_URL": f"postgresql://{p.hostname}{porta}/{banco}?sslmode=require",
    "DB_USERNAME": up.unquote(p.username),
    "DB_PASSWORD": up.unquote(p.password),
    "COOKIE_SECURE": "true",
    "FORWARD_HEADERS_STRATEGY": "framework",
    "DB_POOL": "5",
}
for var, chave in (("CONTATO", "ALERTALAR_CONTATO_EMAIL"), ("ADMIN_EMAIL", "ALERTALAR_ADMIN_EMAIL"),
                   ("ADMIN_SENHA", "ALERTALAR_ADMIN_SENHA")):
    if os.environ.get(var, "").strip():
        env[chave] = os.environ[var].strip()
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(env, f, ensure_ascii=False)
print(p.hostname)
PY
)" || erro "Isso não parece uma connection string do Neon. Ela tem o formato
postgresql://USUARIO:SENHA@ep-....neon.tech/neondb?sslmode=require"
  unset NEON ADMIN_SENHA

  # Região do Cloud Run perto do banco (cada consulta ao site faz várias idas ao banco)
  if [ -z "$REGIAO" ]; then
    case "$HOST_BANCO" in
      *sa-east-1*) REGIAO="southamerica-east1" ;;
      *us-east-1*|*us-east-2*|*eastus*) REGIAO="us-east4" ;;
      *us-west-2*|*westus*) REGIAO="us-west1" ;;
      *eu-central-1*|*eu-west-2*|*germanywestcentral*) REGIAO="europe-west1" ;;
      *ap-southeast-1*) REGIAO="asia-southeast1" ;;
      *ap-southeast-2*) REGIAO="australia-southeast1" ;;
      *) REGIAO="us-central1" ;;
    esac
  fi
fi
REGIAO="${REGIAO:-us-central1}"
echo "Região do Cloud Run: $REGIAO"

# ---------------------------------------------------------------------
titulo "4/5 Montando e publicando (3 a 8 minutos na primeira vez)"
ARGS=(run deploy "$SERVICO" --source . --region "$REGIAO" --allow-unauthenticated
  --port 8080 --memory 512Mi --cpu 1 --cpu-boost --min-instances 0 --max-instances 2
  --concurrency 40 --timeout 120 --quiet)
[ -n "$ARQ_ENV" ] && ARGS+=(--env-vars-file "$ARQ_ENV")
gcloud "${ARGS[@]}"

URL="$(gcloud run services describe "$SERVICO" --region "$REGIAO" --format='value(status.url)')"
echo
echo "Conferindo se o site respondeu..."
SAUDE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 90 "$URL/actuator/health" || true)"
if [ "$SAUDE" = "200" ]; then
  echo "O site está no ar."
else
  aviso "o site ainda não respondeu (código $SAUDE). Veja os registros em: Cloud Run > $SERVICO > Registros (Logs)."
fi

# ---------------------------------------------------------------------
titulo "5/5 Alerta de gastos (opcional)"
read -rp "Receber um e-mail se o gasto do mês passar de 5 (na moeda da sua conta, ex.: R\$ 5)? [S/n] " ALERTA
if [[ ! "${ALERTA:-s}" =~ ^[Nn] ]]; then
  CONTA="$(gcloud billing projects describe "$PROJETO" --format='value(billingAccountName)' 2>/dev/null | sed 's#billingAccounts/##' || true)"
  if [ -z "$CONTA" ]; then
    aviso "não encontrei a conta de faturamento; crie o alerta em Faturamento > Orçamentos e alertas."
  else
    gcloud services enable billingbudgets.googleapis.com --quiet >/dev/null 2>&1 || true
    if gcloud billing budgets list --billing-account="$CONTA" --format='value(displayName)' 2>/dev/null | grep -qx "AlertaLar - alerta de gastos"; then
      echo "O alerta de gastos já existe."
    elif gcloud billing budgets create --billing-account="$CONTA" --display-name="AlertaLar - alerta de gastos" \
        --budget-amount=5 --threshold-rule=percent=0.2 --threshold-rule=percent=1.0 \
        --filter-projects="projects/$PROJETO" --quiet >/dev/null 2>&1; then
      echo "Alerta criado: você recebe um e-mail se o gasto do mês chegar a 1 ou a 5."
    else
      aviso "não foi possível criar o alerta automaticamente; crie em Faturamento > Orçamentos e alertas."
    fi
  fi
fi

titulo "Pronto"
echo "Endereço do AlertaLar: $URL"
echo "Para publicar uma versão nova: rode de novo 'bash implantar-cloud-run.sh' nesta pasta."
