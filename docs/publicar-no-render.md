# Publicar o AlertaLar no Render (gratuito, sem cartão)

O Render roda o AlertaLar a partir do `Dockerfile` e publica de novo sozinho a cada mudança no
GitHub. O plano gratuito não pede cartão. Em troca, o site **dorme depois de 15 minutos sem
visitas** e a primeira visita seguinte espera ele ligar de novo (cerca de 1 minuto). O banco
fica no Neon.

## 1. Criar o serviço (uma vez)

1. Entre em **render.com** e clique em **Get Started**. Escolha **GitHub** para entrar com a sua
   conta do GitHub.
2. Clique em **New +** → **Blueprint**.
3. Em **Connect a repository**, clique em **Configure account** (ou **Connect GitHub**), permita
   o acesso ao repositório **alertalar-python** e volte. Escolha
   **EduardoHenrique90111/alertalar-python**.
4. Dê um nome ao Blueprint (por exemplo, `alertalar-python`). O Render lê o arquivo `render.yaml`
   do projeto e mostra o serviço **alertalar-python** no plano **Free**.
5. Ele pede o valor de **DATABASE_URL**. Cole a **connection string do Neon** (painel do Neon →
   **Connect** → copiar), no formato
   `postgresql://USUARIO:SENHA@ep-....neon.tech/neondb?sslmode=require`.
6. Clique em **Apply** (ou **Deploy Blueprint**). A primeira publicação leva de 3 a 10 minutos.
7. Quando aparecer **Live**, o endereço do site fica no topo da página do serviço, no formato
   `https://alertalar-python.onrender.com` (o Render acrescenta letras se o nome já estiver em uso).

Opcional: em **Environment**, acrescente `ALERTALAR_CONTATO_EMAIL` com um e-mail de contato,
pedido pela política de uso do OpenStreetMap, e `ALERTALAR_ADMIN_EMAIL` e
`ALERTALAR_ADMIN_SENHA` para criar um administrador (senha com 10+ caracteres, letras e números).

### Banco: o mesmo da versão em Java ou um novo

- **Mesmo banco**: cole a mesma connection string usada pelo serviço em Java. A versão em
  Python reconhece as tabelas criadas pelo Flyway e não as recria; contas, consultas e relatos
  ficam compartilhados entre os dois sites.
- **Banco separado**: no Neon, crie outro banco (ou um *branch*) e cole a connection string dele.
  As tabelas e o histórico oficial são criados no primeiro início, que por isso demora um pouco mais.

## 2. Publicar versões novas

Automático: cada mudança no ramo `main` do GitHub gera uma publicação nova no Render.

## 3. Se a primeira visita demorar

É o site acordando. Para ele não dormir, dá para usar um serviço gratuito que visita o
endereço a cada 10 minutos (por exemplo, **cron-job.org**), apontando para
`https://SEU-ENDERECO.onrender.com/actuator/health`. Um serviço ligado o mês inteiro usa cerca
de 744 das 750 horas gratuitas do mês, e essas horas são somadas entre os serviços gratuitos da
conta: com a versão em Java e a em Python, só um dos dois pode ficar sempre acordado.

## Se algo der errado

- **Deploy falhou**: abra o serviço → **Logs**. Logo no início aparece a linha
  `Banco de dados: HOST/BANCO (origem: ...)`. Se ela mostrar `localhost` e "nenhuma variável", a
  `DATABASE_URL` ficou vazia; se aparecer "Configuração inválida" ou "Não foi possível conectar",
  a connection string está errada. Em **Environment**, corrija `DATABASE_URL` (copie pelo botão
  **Copy snippet** do Neon, que traz a senha de verdade) e clique em **Save, rebuild, and deploy**.
- **Memória**: o plano gratuito tem 512 MB; a versão em Python usa cerca de 100 MB.
- **Limite de conexões do Neon**: o `render.yaml` já usa `DB_POOL=5` (até 5 conexões ao banco).
