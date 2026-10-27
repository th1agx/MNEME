#!/usr/bin/env bash
# MNEME: acesso de colaborador ao código cifrado (git-crypt + GPG).
#
# Rode na pasta do repositório clonado:   bash colaborar/acesso.sh
# Windows: use o Git Bash. macOS/Linux: terminal normal.
#
# Este script é público e não contém segredos. A senha da sua chave GPG é
# digitada só por você, na janela do GPG; o script nunca a vê.

set -euo pipefail

amarelo() { printf '\033[33m%s\033[0m\n' "$*"; }
verde()   { printf '\033[32m%s\033[0m\n' "$*"; }
vermelho(){ printf '\033[31m%s\033[0m\n' "$*"; }
passo()   { printf '\n\033[1m%s\033[0m\n' "$*"; }

cd "$(git rev-parse --show-toplevel 2>/dev/null || { vermelho "Rode dentro da pasta do repositório MNEME clonado."; exit 1; })"

cifrado() { head -c 9 src/main.ts 2>/dev/null | grep -q "GITCRYPT"; }

# ---------------------------------------------------------------- 0. já aberto?
if [ -f src/main.ts ] && ! cifrado; then
  verde "O código já está aberto neste computador. Nada a fazer."
  exit 0
fi

# ---------------------------------------------------------------- 1. ferramentas
passo "1/4  Conferindo ferramentas"
falta=0
if ! command -v gpg >/dev/null; then
  vermelho "GPG não encontrado."
  echo "  Windows: instale o Git for Windows (git-scm.com) e rode este script pelo Git Bash."
  echo "  macOS:   brew install gnupg      Linux: sudo apt install gnupg"
  falta=1
fi
if ! command -v git-crypt >/dev/null; then
  vermelho "git-crypt não encontrado."
  echo "  Windows: baixe git-crypt-0.7.0-x86_64.exe em https://github.com/AGWA/git-crypt/releases,"
  echo "           renomeie para git-crypt.exe e coloque na pasta: $(dirname "$(command -v git)")"
  echo "  macOS:   brew install git-crypt  Linux: sudo apt install git-crypt"
  falta=1
fi
[ "$falta" = 0 ] || { amarelo "Instale o que falta e rode de novo."; exit 1; }
verde "gpg e git-crypt instalados."

# ---------------------------------------------------------------- 2. chave GPG
passo "2/4  Sua chave GPG"
minhas_chaves() { gpg --batch --with-colons --list-secret-keys 2>/dev/null | awk -F: '/^fpr:/ {print $10}'; }

if [ -z "$(minhas_chaves)" ]; then
  echo "Você ainda não tem chave GPG neste computador. Vamos criar uma (vale 2 anos)."
  read -r -p "  Seu nome: " nome
  echo "  E-mail: use de preferência o e-mail privado do GitHub (Settings > Emails,"
  echo "  algo como 12345+usuario@users.noreply.github.com) para não expor o pessoal."
  read -r -p "  E-mail: " email
  echo
  amarelo "Vai abrir uma janela pedindo uma SENHA para a chave. Ela é só sua: guarde no gerenciador de senhas."
  gpg --quick-generate-key "$nome <$email>" default default 2y
fi

# Usa a chave principal mais recente.
fpr="$(gpg --batch --with-colons --list-secret-keys 2>/dev/null | awk -F: '/^sec:/ {getline; print $10}' | tail -1)"
uid="$(gpg --batch --with-colons --list-secret-keys "$fpr" 2>/dev/null | awk -F: '/^uid:/ {print $10; exit}')"
verde "Chave: $uid"

# ---------------------------------------------------------------- 3. autorização
passo "3/4  Autorização do dono do projeto"
git pull --quiet 2>/dev/null || true
autorizado=0
for f in $(minhas_chaves); do
  [ -f ".git-crypt/keys/default/0/$f.gpg" ] && autorizado=1
done

if [ "$autorizado" = 0 ]; then
  arquivo="minha-chave-publica.asc"
  gpg --armor --export "$fpr" > "$arquivo"
  echo "Sua chave ainda não foi autorizada. Faça isto:"
  echo
  echo "  a) Publique sua chave PÚBLICA no GitHub: https://github.com/settings/gpg/new"
  echo "     Cole o conteúdo do arquivo $arquivo (criado agora nesta pasta)."
  echo
  echo "  b) Mande ao dono do projeto, por WhatsApp ou ligação (não por e-mail):"
  echo "       - seu usuário do GitHub"
  echo "       - esta impressão digital:"
  echo
  gpg --fingerprint "$fpr" | sed -n '2p' | sed 's/^ */       /'
  echo
  amarelo "Quando ele confirmar a autorização, rode este script de novo."
  exit 0
fi
verde "Sua chave está autorizada."

# ---------------------------------------------------------------- 4. desbloqueio
passo "4/4  Abrindo o código"
# Windows abre no máximo 260 caracteres de caminho; o git-crypt precisa abrir
# .git-crypt/keys/default/0/<impressão digital>.gpg dentro desta pasta.
if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
  total=$(( ${#PWD} + 72 ))
  if [ "$total" -gt 255 ]; then
    vermelho "A pasta tem um caminho longo demais para o Windows ($total de 260 caracteres)."
    amarelo "Clone numa pasta curta e rode o script lá:  cd /c/dev && git clone https://github.com/th1agx/MNEME.git"
    exit 1
  fi
fi
amarelo "Digite a senha da sua chave GPG na janela que vai abrir."
git-crypt unlock
if cifrado; then
  vermelho "Ainda cifrado. Confira a senha e rode de novo."
  exit 1
fi
rm -f minha-chave-publica.asc
verde "Pronto: código aberto. Commits que você fizer voltam cifrados automaticamente."
echo "Próximo passo: leia docs/operacao.md."
