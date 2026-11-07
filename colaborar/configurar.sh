#!/usr/bin/env bash
# Prepara este computador para trabalhar no MNEME: acesso à Oracle, Python, testes e Knowledge Vault no Obsidian.
# Uso, na raiz do repositório: bash colaborar/configurar.sh   (macOS, Linux ou Git Bash no Windows)
# Pode rodar de novo quantas vezes quiser: só refaz o que falta.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
SO="$(uname -s)"
passo() { printf '\n== %s\n' "$1"; }

passo "1/5 Chaves (.env)"
if [ ! -f .env ]; then
  echo "Falta o arquivo .env na raiz do repositório."
  echo "Copie para $REPO/.env o bloco do e-mail de chaves do MNEME e rode de novo."
  exit 1
fi
ler() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '\r'; }
for chave in SIGNALS_REST_URL SIGNALS_API_KEY MNEME_SSH_KEY_B64; do
  [ -n "$(ler "$chave")" ] || { echo "Falta $chave no .env. Confira o bloco do e-mail."; exit 1; }
done
echo "ok"

passo "2/5 Acesso à Oracle (ssh mneme-a1)"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
CHAVE="$HOME/.ssh/mneme-oracle"
ler MNEME_SSH_KEY_B64 | base64 --decode > "$CHAVE.novo"
if [ -f "$CHAVE" ] && cmp -s "$CHAVE" "$CHAVE.novo"; then rm -f "$CHAVE.novo"; else mv "$CHAVE.novo" "$CHAVE"; fi
chmod 600 "$CHAVE"
if ! grep -qE "^Host mneme-a1$" "$HOME/.ssh/config" 2>/dev/null; then
  cat >> "$HOME/.ssh/config" <<EOF

Host mneme-a1
  HostName 147.15.63.149
  User ubuntu
  IdentityFile ~/.ssh/mneme-oracle
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  ServerAliveInterval 30
EOF
  chmod 600 "$HOME/.ssh/config"
fi
if ssh -o BatchMode=yes -o ConnectTimeout=15 mneme-a1 true; then
  echo "ok: conectado à A1"
else
  echo "Sem acesso à A1. Confira a internet e se a chave do e-mail é a atual."
  exit 1
fi

passo "3/5 Python (uv) e dependências"
UV="$(command -v uv || true)"
[ -n "$UV" ] || for c in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do [ -x "$c" ] && UV="$c"; done
if [ -z "$UV" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  UV="$HOME/.local/bin/uv"
fi
(cd robo && "$UV" sync -q)
echo "ok"

passo "4/5 Testes"
(cd robo && "$UV" run pytest -q 2>&1 | tail -1)

passo "5/5 Knowledge Vault (Obsidian)"
SINCRONIZAR="$REPO/colaborar/sincronizar-vault.sh"
bash "$SINCRONIZAR"
tail -1 "$HOME/.mneme/vault.log"
case "$SO" in
  Darwin)
    PLIST="$HOME/Library/LaunchAgents/com.mneme.vault.plist"
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mneme.vault</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$SINCRONIZAR</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "Agendado no launchd (com.mneme.vault), a cada 10 minutos."
    ;;
  Linux)
    LINHA="*/10 * * * * /bin/bash '$SINCRONIZAR'"
    (crontab -l 2>/dev/null | grep -v "sincronizar-vault.sh"; echo "$LINHA") | crontab -
    echo "Agendado no cron, a cada 10 minutos."
    ;;
  MINGW*|MSYS*|CYGWIN*)
    BASH_WIN="$(cygpath -w "$(command -v bash)")"
    SCRIPT_WIN="$(cygpath -w "$SINCRONIZAR")"
    schtasks //Create //F //SC MINUTE //MO 10 //TN "MNEME Vault" //TR "\"$BASH_WIN\" \"$SCRIPT_WIN\"" >/dev/null
    echo "Agendado no Agendador de Tarefas do Windows (MNEME Vault), a cada 10 minutos."
    ;;
  *) echo "Sistema $SO sem agendamento automático: rode bash colaborar/sincronizar-vault.sh quando quiser." ;;
esac

printf '\nPronto. No Obsidian: "Open folder as vault" e escolha %s/vault\n' "$REPO"
echo "Log da sincronização: $HOME/.mneme/vault.log · backups: $HOME/.mneme/vault-backups"
