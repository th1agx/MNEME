# MNEME na Cloudflare (primeira etapa)

## Estrutura

- **Pages** publica a interface estática em `public/`.
- **Pages Functions / Workers** encaminha `/api/*` para o servidor Node do MNEME na VPS. O bot continua rodando na VPS, com o feed e o monitor de posições ativos.
- **D1 (`mneme-operational`)** guarda a estrutura inicial para configurações, eventos, sinais, posições, ordens, ranking e auditoria. A migração cria as tabelas, mas o bot ainda usa seus repositórios JSON/JSONL; conectá-lo ao D1 exige implementar adaptadores.
- **KV (`mneme-cache`)** fica reservado para cache descartável. Não guardar nele posições, ordens, configurações ou decisões de execução.
- **Turso** será avaliado depois para categorias específicas de dados, com proprietário e fluxo de escrita definidos. Evitar gravar a mesma informação operacional em D1 e Turso.

## Recursos criados

- Pages: `mneme-dashboard` — `https://mneme-dashboard.pages.dev`
- Worker Functions: configuração em `wrangler.jsonc` e código em `functions/api/`
- D1: `mneme-operational`; migração `migrations/0001_operational.sql`
- KV: `mneme-cache`

## Conectar a VPS

Configure `MNEME_API_ORIGIN` no ambiente de produção do projeto Pages como a origem HTTPS do servidor do MNEME, sem caminho `/api`. A rota Worker mantém os caminhos `/api/...`, incluindo o stream de eventos.

Se a origem estiver protegida pelo Cloudflare Access, crie um Service Token e configure `CF_ACCESS_CLIENT_ID` e `CF_ACCESS_CLIENT_SECRET` como secrets do Pages. Não salve esses valores no Git nem no código do navegador. A autenticação Basic do servidor do MNEME continua sendo encaminhada para o bot.

Até `MNEME_API_ORIGIN` ser configurada, as rotas `/api/*` respondem 503 de propósito; nenhuma informação do bot é servida pelo Pages. A página já está publicada, mas ainda não está ligada ao bot ativo.

## Desenvolvimento e publicação

Esta conta foi configurada por Wrangler a partir do checkout local desbloqueado. O repositório criptografa arquivos novos por padrão; por isso, um build hospedado pelo GitHub que clone o repositório sem a chave git-crypt não consegue compilar `wrangler.jsonc` nem `functions/api/`. Não alterar `.gitattributes` para contornar isso sem solicitação explícita do dono do projeto. A automação usa um runner self-hosted no ambiente desbloqueado, conforme abaixo.

## Autodeploy por Git

O workflow `.github/workflows/deploy-cloudflare.yml` publica no Pages quando há push para `main`. Ele usa um **runner self-hosted** e um clone de deploy separado, desbloqueado com git-crypt, porque o runner hospedado pelo GitHub recebe os arquivos cifrados.

Configuração necessária no repositório que fará o deploy:

1. Usar um repositório sob sua administração (por exemplo, um fork seu). A conta atual tem acesso de escrita ao repositório original, mas não permissão administrativa para registrar nele um runner.
2. No fork, abrir **Settings > Actions > Runners > New self-hosted runner** e seguir as instruções apresentadas para Linux. No servidor da VPS, criar um clone dedicado de deploy a partir do fork e desbloqueá-lo pelo fluxo oficial de colaborador. Registrar o runner com a etiqueta `mneme-cloudflare`. Não reutilizar a pasta de trabalho do bot.
3. Definir a variável Actions `MNEME_DEPLOY_CHECKOUT` com o caminho absoluto desse clone. `CLOUDFLARE_ACCOUNT_ID` já foi cadastrada no fork.
4. Criar um API Token na Cloudflare com `Cloudflare Pages:Edit` e `D1:Edit`, restritos à sua conta; guardar o valor em **Settings > Secrets and variables > Actions > Secrets** como `CLOUDFLARE_API_TOKEN`. A documentação exige Pages Edit para publicar pelo Pages API e D1 Edit para executar escritas no D1 ([Pages](https://developers.cloudflare.com/pages/configuration/api/), [permissões de API](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)).
5. Com o runner ativo e as variáveis/secrets configurados, fazer push em `main`; o runner atualiza o clone desbloqueado, aplica migrações pendentes e publica os assets e as Pages Functions.

O runner é necessário porque uma pipeline hospedada pelo GitHub não tem acesso à chave git-crypt. Isso mantém a chave fora dos secrets e dos serviços de build hospedados. O runner e o checkout de deploy precisam permanecer ativos e confiáveis; o runner só deve aceitar workflows do repositório controlado por você.
