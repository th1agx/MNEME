# MNEME na Cloudflare (primeira etapa)

## Estrutura

- **Pages** publica a interface estática em `public/`.
- **Pages Functions / Workers** encaminha `/api/*` para o servidor Node do MNEME na VPS. O bot continua rodando na VPS, com o feed e o monitor de posições ativos. A API do navegador continua recebendo estado em tempo real e enviando comandos ao bot.
- **D1 (`mneme-operational`)** tem o esquema inicial para eventos, sinais, posições, ordens, ranking e auditoria. O esquema está aplicado, mas ainda não há ingestão: o bot continua usando seus repositórios JSON/JSONL na VPS. D1 começa como cópia histórica/analítica; o bot permanece a fonte de verdade para decisões e execução.
- **KV (`mneme-cache`)** fica reservado para cache descartável. Não guardar nele posições, ordens, configurações ou decisões de execução. O código ainda não usa esse binding.
- **Turso** será avaliado depois para categorias específicas de dados, com proprietário e fluxo de escrita definidos. Evitar gravar a mesma informação operacional em D1 e Turso.

## Recursos criados

- Pages: projeto `mneme` — `https://mneme-1b8.pages.dev`
- Worker Functions: configuração em `wrangler.jsonc` e código em `functions/api/`
- D1: `mneme-operational`; migração `migrations/0001_operational.sql`
- KV: `mneme-cache`

## Conectar a VPS

Configure `MNEME_API_ORIGIN` no ambiente de produção do projeto Pages como a origem HTTPS do servidor do MNEME, sem caminho `/api`. A rota Worker mantém os caminhos `/api/...`, incluindo o stream de eventos.

O bot do Telegram e a API HTTP do MNEME são interfaces diferentes do mesmo serviço. O Telegram não fornece a URL que o Pages precisa. Como ainda não há domínio, é possível abrir um **Quick Tunnel temporário** na VPS, aproveitando o serviço `cloudflared` já definido em `docker-compose.yml`:

```bash
docker compose --profile cloudflare run --rm --no-deps \
  -e TUNNEL_TOKEN= cloudflared \
  tunnel --no-autoupdate --url http://mneme:4740
```

O terminal imprime uma URL `https://....trycloudflare.com`; mantenha esse processo ativo e use apenas a origem (sem `/api`) no `MNEME_API_ORIGIN` do Pages. Essa URL temporária muda quando o túnel é encerrado ou reiniciado, então será preciso atualizar a variável. Para endereço estável, será necessário configurar um domínio e um túnel nomeado.

Antes de ligar a API, restrinja o endereço `mneme-1b8.pages.dev` com Cloudflare Access e uma política *Allow* para o seu e-mail. Esse cuidado é necessário porque a API inclui comandos de pausa, retomada e fechamento de posição; o cabeçalho `x-mneme` do navegador é proteção contra CSRF, não autenticação. Nas configurações do Pages, habilite a política de Access e confira em **Zero Trust > Access > Applications** que ela cobre o host de produção `mneme-1b8.pages.dev` (a configuração padrão pode cobrir apenas os previews). Veja [como proteger o domínio `pages.dev`](https://developers.cloudflare.com/pages/platform/known-issues/).

Se a origem estiver protegida pelo Cloudflare Access, crie um Service Token e configure `CF_ACCESS_CLIENT_ID` e `CF_ACCESS_CLIENT_SECRET` como secrets do Pages. Não salve esses valores no Git nem no código do navegador. A autenticação Basic do servidor do MNEME continua sendo encaminhada para o bot.

Até `MNEME_API_ORIGIN` ser configurada, as rotas `/api/*` respondem 503 de propósito; nenhuma informação do bot é servida pelo Pages. A página já está publicada, mas ainda não está ligada ao bot ativo.

## Dados e integração

O fluxo de leitura do painel é `navegador → Pages/Worker → API HTTPS do bot na VPS`. O Worker não consulta D1 para montar o painel. O fluxo de escrita de configurações e comandos também termina no bot, que persiste os dados operacionais em `data/`.

O fluxo do produto é o ranking dos traders do Top → coletor e motor de sinais na VPS → painel interno + distribuição no Telegram. O provedor de sinais fica configurado na VPS; a API do bot alimenta o painel.

Rotas já implementadas no bot e encaminhadas pelo Worker:

| Rota | Uso |
|---|---|
| `GET /api/health` | Saúde do bot e do feed |
| `GET /api/state` | Snapshot atual do painel |
| `GET /api/stream` | Atualizações em tempo real via SSE |
| `GET/PUT /api/settings` | Ler e salvar configurações |
| `POST /api/pause`, `POST /api/resume` | Controle do bot |
| `POST /api/positions/:id/close` | Fechar uma posição |

O D1 remoto já contém as tabelas da migração `0001_operational.sql`; no momento da conferência, `trader_events`, `signals`, `positions` e `orders` estavam vazias. O binding `MNEME_DB` está pronto para uma etapa de ingestão. Essa etapa ainda precisa de um endpoint interno autenticado e de envio idempotente pelo bot (por exemplo, `event_id` para eventos), com fila/repetição local para que falhas de rede nunca parem o feed ou a execução.

O Telegram implementado hoje é operacional: `TELEGRAM_CHAT_ID` seleciona um único chat, recebe notificações e pode enviar comandos administrativos. Ele ainda não tem cadastro de assinantes, cobrança, validade de acesso ou entrega individual para clientes. A distribuição paga deve ser um componente separado, sem acesso aos comandos de negociação do bot administrativo. Quando o modelo de cobrança for definido, o D1 pode receber assinantes/entitlements, eventos de pagamento normalizados e recibos de entrega idempotentes; o provedor de pagamento fica atrás de uma interface para não prender a arquitetura a um provedor antes da escolha.

Separação inicial proposta:

| Dado | Fonte de verdade agora | Destino futuro |
|---|---|---|
| Configuração, pausa e execução | Bot na VPS | Continua no bot; não replicar decisões para KV |
| Eventos e sinais | Bot na VPS | Espelho histórico no D1 |
| Posições e ordens | Bot na VPS | Espelho no D1 para consulta e histórico |
| Cache transitório de consultas externas | Fonte externa | KV, com validade curta |
| Acesso e entrega a assinantes do Telegram | Ainda não existe | D1, depois da definição da cobrança |
| Dados volumosos de integrações específicas | A definir | Turso, quando a conta e as categorias estiverem definidas |

Assim, primeiro conectar `MNEME_API_ORIGIN` faz o painel mostrar os dados atuais do bot. A ingestão para D1 é uma etapa separada; criar as tabelas não importa automaticamente os arquivos JSON/JSONL existentes. Não migre os arquivos de posições/ordens para outra fonte sem definir reconciliação e backup.

## Desenvolvimento e publicação

O workflow `.github/workflows/deploy-cloudflare.yml` usa um runner hospedado pelo GitHub. Não precisa de uma VPS para publicar o Pages. O repositório continua cifrado por padrão; só os arquivos necessários ao deploy ficam em texto aberto e, como o repositório é público, qualquer pessoa pode lê-los.

Os caminhos públicos são `public/**`, `functions/**`, `migrations/**`, `wrangler.jsonc`, `scripts/prepare-pages.sh`, `package.json` e `tsconfig.json`, além do workflow em `.github/workflows/`. Eles contêm a interface, o proxy do Pages, o esquema do D1 e a configuração necessária para compilar e publicar. O código do bot em `src/` e os demais arquivos permanecem cifrados. Nunca coloque credenciais ou chaves privadas nos caminhos públicos.

Em cada push para `main` que altere esses caminhos, o workflow prepara uma cópia temporária de `public/`, minifica e ofusca os JavaScript, aplica migrações D1 pendentes e publica Pages/Functions no projeto `mneme` (`mneme-1b8.pages.dev`). Também pode ser iniciado manualmente em **Actions > Deploy MNEME to Cloudflare > Run workflow**.

Configure no GitHub, em **Settings > Secrets and variables > Actions**:

- Variável `CLOUDFLARE_ACCOUNT_ID` com o ID da conta.
- Secret `CLOUDFLARE_API_TOKEN` com permissões `Cloudflare Pages:Edit` e `D1:Edit`, restrito à conta ([permissões de Pages](https://developers.cloudflare.com/pages/configuration/api/), [permissões de API](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)).

As chaves da API do bot não vão para o workflow nem para o navegador. `MNEME_API_ORIGIN`, `CF_ACCESS_CLIENT_ID` e `CF_ACCESS_CLIENT_SECRET` são configurações de runtime do Pages; cadastre o Client ID e o Client Secret como secrets nas configurações de produção do projeto Pages. Não inclua esses valores no Git.
