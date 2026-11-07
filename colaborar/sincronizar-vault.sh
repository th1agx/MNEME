#!/usr/bin/env bash
# Sincroniza o Knowledge Vault entre o Obsidian deste computador e o repositório central na Oracle.
# Agendado a cada 10 minutos pelo configurar.sh. Se o computador estiver desligado, a Oracle segue sem ele.
# Conflito: vale a edição feita aqui (a pessoa); o Git guarda as duas versões no histórico.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PASTA="${MNEME_VAULT:-$REPO/vault}"
REMOTO="${MNEME_VAULT_REMOTO:-mneme-a1:mneme/robo/dados/vault/hub.git}"
SUPORTE="${MNEME_SUPORTE:-$HOME/.mneme}"
BACKUPS="$SUPORTE/vault-backups"
LOG="$SUPORTE/vault.log"
mkdir -p "$BACKUPS" "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "== $(date '+%F %T')"

# Uma sincronização por vez (o macOS e o Git Bash não têm flock).
TRAVA="$SUPORTE/vault.trava"
if ! mkdir "$TRAVA" 2>/dev/null; then
  if [ -n "$(find "$TRAVA" -maxdepth 0 -mmin +30)" ]; then rmdir "$TRAVA"; mkdir "$TRAVA"; else echo "outra sincronização em andamento"; exit 0; fi
fi
trap 'rmdir "$TRAVA"' EXIT

if [ ! -d "$PASTA/.git" ]; then
  git clone -q "$REMOTO" "$PASTA" || { echo "clone falhou"; exit 1; }
  git -C "$PASTA" config user.name "Obsidian de $(whoami)"
  git -C "$PASTA" config user.email "$(whoami)@obsidian.local"
fi
cd "$PASTA"

git add -A
git diff --cached --quiet || git commit -qm "Edição no Obsidian $(date '+%F %T')"

# Backup diário do que está no Mac, antes de misturar com a Oracle. Guarda 14.
HOJE="$BACKUPS/vault-$(date +%Y%m%d).bundle"
[ -f "$HOJE" ] || git bundle create -q "$HOJE" --all
ls -1t "$BACKUPS"/vault-*.bundle 2>/dev/null | tail -n +15 | while read -r velho; do rm -f "$velho"; done

if ! git fetch -q origin; then echo "Oracle fora de alcance; tenta no próximo ciclo"; exit 0; fi
if git rev-parse -q --verify origin/main >/dev/null; then
  if ! git merge -q --no-edit -X ours origin/main; then
    git merge --abort
    echo "CONFLITO sem solução automática; nada foi misturado"
    exit 1
  fi
fi
git push -q origin HEAD:main || echo "envio recusado (a Oracle gravou no meio); tenta no próximo ciclo"
echo "ok $(git rev-parse --short HEAD)"
