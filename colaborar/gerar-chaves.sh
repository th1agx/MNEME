#!/usr/bin/env bash
# Só para o dono: gera privado/chaves-colaboradores.md com o .env completo, para mandar aos colaboradores.
# A pasta privado/ é ignorada pelo Git: o arquivo nunca vai para o GitHub.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
CHAVE="${1:-$HOME/.ssh/mneme-oracle}"
[ -f .env ] || { echo "Falta o .env na raiz."; exit 1; }
[ -f "$CHAVE" ] || { echo "Falta a chave SSH da Oracle em $CHAVE."; exit 1; }

# A chave de acesso à A1 entra no .env, codificada numa linha.
NOVA="MNEME_SSH_KEY_B64=$(base64 < "$CHAVE" | tr -d '\n')"
if grep -qE "^MNEME_SSH_KEY_B64=" .env; then
  grep -vE "^MNEME_SSH_KEY_B64=" .env > .env.novo && echo "$NOVA" >> .env.novo && mv .env.novo .env
else
  printf '\n# Acesso à Oracle A1 (colaborar/configurar.sh grava em ~/.ssh/mneme-oracle)\n%s\n' "$NOVA" >> .env
fi
chmod 600 .env

mkdir -p privado
SAIDA="privado/chaves-colaboradores.md"
{
  echo "# Chaves do MNEME"
  echo
  echo "Confidencial. Não encaminhe, não publique e não coloque no Git. Gerado em $(date '+%d/%m/%Y %H:%M')."
  echo
  echo "## Como usar"
  echo
  echo "1. Clone o repositório: \`git clone https://github.com/th1agx/MNEME.git\`"
  echo "2. Na raiz do repositório, crie o arquivo \`.env\` com o bloco abaixo, exatamente como está."
  echo "3. Rode \`bash colaborar/configurar.sh\` (no Windows, pelo Git Bash)."
  echo "4. No Obsidian, abra a pasta \`vault\` do repositório (\"Open folder as vault\")."
  echo
  echo "## Bloco do .env"
  echo
  echo '```'
  grep -vE '^[[:space:]]*$' .env
  echo '```'
} > "$SAIDA"
chmod 600 "$SAIDA"
echo "Gerado: $REPO/$SAIDA ($(grep -cE '^[A-Z0-9_]+=' .env) chaves)"
