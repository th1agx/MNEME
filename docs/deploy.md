# MNEME: rodar 24 horas num servidor

Com dinheiro real, o bot precisa ficar ligado o tempo todo: se o computador dormir, nenhum stop é executado. O jeito mais simples é uma VPS Linux pequena com Docker.

## 1. Servidor

Qualquer VPS com 1 vCPU, 1 GB de RAM e Ubuntu 24.04 serve (Hetzner, DigitalOcean, Vultr, Contabo…). Escolha uma região próxima dos servidores da Solana e do Jupiter: EUA ou Europa têm menos atraso que o Brasil.

Instale o Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

## 2. Código e configuração

O código é criptografado (docs/criptografia.md). Instale o git-crypt, envie a chave para a VPS sem passar por chat ou e-mail (por exemplo `scp mneme-git-crypt.key usuario@ip-da-vps:~/`) e desbloqueie:

```bash
sudo apt install -y git-crypt
git clone https://github.com/th1agx/MNEME.git mneme
cd mneme
git-crypt unlock ~/mneme-git-crypt.key
shred -u ~/mneme-git-crypt.key
cp .env.example .env
nano .env
```

O `shred` apaga a cópia da chave depois do desbloqueio; o repositório continua desbloqueado.

No `.env`, além das chaves, defina `MNEME_PASSWORD` com uma senha longa: o contêiner exige senha porque escuta em todas as interfaces internamente.

Prepare a pasta de dados para o usuário do contêiner (uid 1000):

```bash
mkdir -p data
sudo chown 1000:1000 data
```

## 3. Subir

```bash
docker compose up -d --build
docker compose logs -f
```

Com `restart: unless-stopped`, o MNEME volta sozinho se cair ou se o servidor reiniciar. O Docker também checa `/api/health` a cada minuto.

## 4. Acessar o painel

O painel só aceita conexões da própria VPS (`127.0.0.1:4740`). No seu computador, abra um túnel SSH:

```bash
ssh -L 4740:127.0.0.1:4740 usuario@ip-da-vps
```

E acesse http://localhost:4740 (usuário qualquer, senha do `MNEME_PASSWORD`). Assim o painel nunca fica exposto na internet.

## 4b. Acessar de qualquer lugar pela Cloudflare (recomendado)

O **Cloudflare Tunnel** publica o painel num endereço seu (ex.: `mneme.seudominio.com`) sem abrir nenhuma porta na VPS, e o **Cloudflare Access** exige login antes de mostrar a página. Precisa de uma conta Cloudflare (grátis) com um domínio seu nela.

1. **Túnel:** no painel da Cloudflare, abra *Zero Trust > Networks > Tunnels > Create a tunnel*, escolha *Cloudflared*, dê o nome `mneme` e copie o **token** que aparece no comando de instalação (o texto longo depois de `--token`).
2. **Endereço:** na aba *Public Hostname* do túnel, adicione: subdomínio `mneme`, seu domínio, tipo `HTTP`, URL `mneme:4740`.
3. **Login:** em *Zero Trust > Access > Applications > Add an application > Self-hosted*, use o mesmo endereço (`mneme.seudominio.com`) e crie uma política *Allow* só com o seu e-mail. O método *One-time PIN* manda um código para o e-mail a cada login.
4. **Ligar:** coloque `CLOUDFLARE_TUNNEL_TOKEN=` no `.env` e suba com o perfil da Cloudflare:

```bash
docker compose --profile cloudflare up -d
```

Pronto: abra `https://mneme.seudominio.com`, faça o login da Cloudflare e depois a senha do `MNEME_PASSWORD`. Duas camadas de proteção, porque esse painel pode mandar o bot vender.

A Cloudflare só cuida do acesso ao painel. O bot em si continua rodando na VPS: ele precisa ficar ligado o tempo todo com o feed aberto, e a plataforma de Workers da Cloudflare só executa código por requisição.

## 5. Avisos e comandos no celular (Telegram)

1. No Telegram, fale com **@BotFather**, envie `/newbot` e copie o token.
2. Mande qualquer mensagem para o seu bot novo.
3. Abra `https://api.telegram.org/bot<TOKEN>/getUpdates` e copie o número em `"chat":{"id": ...}`.
4. Coloque `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env` e reinicie: `docker compose up -d`.

O bot avisa sinais, compras, vendas, quedas do feed, falhas de venda e pausas automáticas. Para receber menos mensagens, use `TELEGRAM_MIN_LEVEL=trade` (só operações e problemas).

Também dá para controlar o bot pelo chat:

| Comando | O que faz |
|---|---|
| `/status` | Modo, feed, saldo, exposição e resultado |
| `/posicoes` | Posições abertas com resultado |
| `/pausar` / `/retomar` | Pausa ou retoma novas entradas (saídas continuam) |
| `/vender TOKEN` | Mostra a posição e pede confirmação; `/vender TOKEN sim` vende |

O bot só obedece ao chat do `TELEGRAM_CHAT_ID` e, ao reiniciar, ignora comandos antigos. Para só receber avisos, sem comandos: `TELEGRAM_COMMANDS=off`.

## 6. Atualizar

```bash
git pull
docker compose up -d --build
```

Posições, sinais e configurações ficam em `data/` e sobrevivem às atualizações.

## 7. Backup

`data/live/` guarda o histórico (posições, ordens, sinais, auditoria). Copie de vez em quando:

```bash
tar czf mneme-backup-$(date +%F).tgz data/live
```

A chave da carteira fica só no `.env`. Guarde-a também num gerenciador de senhas.
