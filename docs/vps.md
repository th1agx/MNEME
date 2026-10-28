# MNEME: preparar a VPS (bot + runner de deploy)

Uma VPS roda três coisas, isoladas por usuário:

| Usuário | O que roda | Acessa |
|---|---|---|
| `mneme` | o bot (Docker) e o túnel da Cloudflare | `/opt/mneme` e o `.env` com as chaves da carteira |
| `gha` | o runner do GitHub Actions e o clone de deploy | só `/opt/mneme-deploy`; **não** lê o `.env` do bot |
| você (`admin`) | manutenção, com `sudo` | tudo |

O runner executa código vindo do GitHub; por isso ele nunca roda como o mesmo usuário do bot nem tem `sudo`.

## 1. Escolher e criar a VPS

Recomendação: **Hetzner Cloud CX22** (2 vCPU, 4 GB RAM, ~€5/mês) ou **DigitalOcean Basic** (2 GB, ~US$12/mês com 2 GB). Mínimo de 2 GB de RAM: o deploy compila e roda o `wrangler`. Escolha uma região nos **EUA (Ashburn/Virgínia)** ou na **Europa (Frankfurt/Nuremberg)**, mais perto dos serviços de Solana. Sistema: **Ubuntu 24.04**.

1. Crie a conta no provedor e cadastre o pagamento.
2. No seu Windows, gere uma chave SSH (se ainda não tiver) e copie a parte pública:

   ```bash
   ssh-keygen -t ed25519 -C "mneme-vps"
   cat ~/.ssh/id_ed25519.pub
   ```

3. Ao criar o servidor, cole essa chave pública em *SSH keys*. Não use acesso por senha.
4. Anote o IP do servidor.

## 2. Primeiro acesso e proteção básica

```bash
ssh root@IP_DA_VPS
apt update && apt -y upgrade
apt -y install ufw fail2ban unattended-upgrades git git-crypt gnupg curl ca-certificates

# Seu usuário de manutenção, com a mesma chave SSH
adduser --disabled-password --gecos "" admin
usermod -aG sudo admin
mkdir -p /home/admin/.ssh && cp ~/.ssh/authorized_keys /home/admin/.ssh/
chown -R admin:admin /home/admin/.ssh && chmod 700 /home/admin/.ssh
passwd admin                      # senha para o sudo (só sua)

# SSH só com chave, sem root
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# Firewall: só SSH. O painel e a API saem pelo túnel da Cloudflare, sem porta aberta.
ufw allow OpenSSH && ufw --force enable
dpkg-reconfigure -f noninteractive unattended-upgrades
```

Antes de fechar essa sessão, teste em outro terminal: `ssh admin@IP_DA_VPS`.

## 3. Node.js e Docker

```bash
ssh admin@IP_DA_VPS
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt -y install nodejs
curl -fsSL https://get.docker.com | sudo sh
node --version && docker --version
```

## 4. O bot (usuário `mneme`)

```bash
sudo adduser --system --group --home /opt/mneme --shell /bin/bash mneme
sudo usermod -aG docker mneme
sudo -iu mneme
git clone https://github.com/th1agx/MNEME.git && cd MNEME
bash colaborar/acesso.sh          # desbloqueia com a sua senha de acesso
cp .env.example .env && chmod 600 .env && nano .env
mkdir -p data
exit
sudo chown 1000:1000 /opt/mneme/MNEME/data     # usuário do contêiner
sudo -iu mneme bash -c "cd MNEME && docker compose --profile cloudflare up -d --build"
```

Detalhes do `.env`, Telegram e Cloudflare Tunnel: [deploy.md](deploy.md).

## 5. Runner do GitHub Actions (usuário `gha`)

```bash
sudo adduser --system --group --home /opt/mneme-deploy --shell /bin/bash gha
sudo -iu gha
```

No GitHub: **th1agx/MNEME → Settings → Actions → Runners → New self-hosted runner → Linux**. Rode, como `gha`, os comandos que a página mostrar (download e `./config.sh`). No `config.sh`:

- nome do runner: `mneme-vps`
- rótulo adicional: **`mneme-cloudflare`**

Depois volte para o `admin` e instale como serviço:

```bash
exit
cd /opt/mneme-deploy/actions-runner
sudo ./svc.sh install gha && sudo ./svc.sh start
```

## 6. Clone de deploy (usuário `gha`)

```bash
sudo -iu gha
git clone https://github.com/th1agx/MNEME.git /opt/mneme-deploy/MNEME
cd /opt/mneme-deploy/MNEME
bash colaborar/acesso.sh
git status                        # precisa estar limpo
exit
```

No GitHub, em **Settings → Secrets and variables → Actions → Variables**, crie `MNEME_DEPLOY_CHECKOUT` = `/opt/mneme-deploy/MNEME`. O `CLOUDFLARE_ACCOUNT_ID` pode ficar como secret ou variável; o workflow aceita os dois.

Confira o runner como **Idle** em *Settings → Actions → Runners* e rode *Actions → Deploy MNEME to Cloudflare → Run workflow*.

## 7. Proteção do runner num repositório público

Runner próprio em repositório público só é seguro se código de estranhos não rodar nele:

- **Settings → Actions → General → Fork pull request workflows from outside collaborators:** *Require approval for all outside collaborators*.
- Nunca use `pull_request` em jobs com `runs-on: self-hosted`; o deploy só roda em `push` na `main` e manualmente.
- O usuário `gha` não tem `sudo` nem acesso a `/opt/mneme`; confira com `sudo -u gha cat /opt/mneme/MNEME/.env` (deve dar *Permission denied*).

## 8. Ligar o site à API do bot

O site no Pages encaminha `/api/*` para a API do bot. A API fica atrás do Cloudflare Access, e o Pages entra com um token de serviço:

1. **Zero Trust → Networks → Tunnels →** túnel do MNEME → *Public Hostname*: `api.SEUDOMINIO` → `HTTP` → `mneme:4740`.
2. **Zero Trust → Access → Service Auth → Create Service Token**; guarde o *Client ID* e o *Client Secret*.
3. **Access → Applications →** aplicação self-hosted para `api.SEUDOMINIO` com política **Service Auth** usando esse token.
4. **Pages → projeto mneme → Settings → Variables and Secrets** (produção):
   - `MNEME_API_ORIGIN` = `https://api.SEUDOMINIO`
   - `CF_ACCESS_CLIENT_ID` e `CF_ACCESS_CLIENT_SECRET` (como *Secret*)
5. Faça um novo deploy e verifique: `https://mneme-1b8.pages.dev/api/health` deve responder **200**.

O túnel exige um domínio seu na Cloudflare (dá para registrar pela própria Cloudflare).
