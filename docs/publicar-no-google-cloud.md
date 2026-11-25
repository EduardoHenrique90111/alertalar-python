# Publicar o AlertaLar no Google Cloud Run

O Cloud Run roda o AlertaLar a partir do `Dockerfile`, desliga sozinho quando ninguém está
usando e só cobra CPU enquanto atende alguém. O nível gratuito mensal inclui 180 mil segundos de
CPU, 360 mil GiB-segundos de memória e 2 milhões de requisições. O banco fica no Neon.

## 1. Conta e projeto (uma vez)

1. Entre em **console.cloud.google.com** com sua conta Google e aceite os termos.
2. Ative o faturamento (cadastro de cartão). Contas novas ganham um período de teste gratuito;
   quando ele acabar, o Google pede para ativar a conta completa. Para o site continuar no ar,
   ative-a: dentro do nível gratuito do Cloud Run não há cobrança.
3. Use o projeto criado automaticamente ("My First Project") ou crie um em
   **Selecionar projeto → Novo projeto**.

## 2. Publicar

1. No topo do console, clique no ícone **>_ (Ativar Cloud Shell)**. Abre um terminal no navegador.
2. Leve o projeto até o Cloud Shell:
   ```bash
   git clone https://github.com/EduardoHenrique90111/alertalar-python && cd alertalar-python
   ```
   (repositório privado: o GitHub pede usuário e um token de acesso no lugar da senha). Também
   dá para enviar um `.zip` do projeto pelo menu **⋮ → Fazer upload** do Cloud Shell.
3. Rode:
   ```bash
   bash implantar-cloud-run.sh
   ```
4. Quando pedir, cole a **connection string do Neon** (painel do Neon → **Connect** → copiar).
   Ela não aparece na tela enquanto você cola. O e-mail de contato e o administrador são
   opcionais: o administrador que já existe no banco continua valendo.
5. A primeira publicação leva de 3 a 8 minutos. No fim aparece o endereço do site, no formato
   `https://alertalar-python-....run.app`.

O arquivo escolhe a região do Cloud Run mais perto do banco do Neon (cada página faz várias
consultas ao banco), usa 512 MB de memória, limita o serviço a 2 instâncias e, se você aceitar,
cria um alerta por e-mail caso haja gasto no mês (a partir de 1 na moeda da conta).

## 3. Publicar uma versão nova

Leve a versão nova para o Cloud Shell (`git pull` ou novo .zip) e rode
`bash implantar-cloud-run.sh` de novo. Aperte **Enter** quando perguntar se quer manter a
configuração atual.

## Se algo der errado

- **"sem conta de faturamento"**: em **Faturamento**, vincule a conta ao projeto e rode de novo.
- **Falha de permissão na compilação** (`PERMISSION_DENIED` ou `storage.objects.get`): em
  **IAM e administrador → IAM**, dê o papel **Cloud Run Builder** à conta
  `NUMERO-compute@developer.gserviceaccount.com` e rode de novo.
- **O site não abre**: veja **Cloud Run → alertalar-python → Registros**. A causa mais comum é a
  connection string errada; rode o arquivo de novo, responda **n** para trocar a configuração e
  cole a string certa.
