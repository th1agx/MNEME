#!/usr/bin/env bash
# MNEME: acesso de colaborador ao código cifrado (git-crypt + senha pessoal).
#
# Rode na pasta do repositório clonado:   bash colaborar/acesso.sh
# Windows: use o Git Bash. macOS/Linux: terminal normal.
#
# Este script é público e não contém segredos. Cada colaborador tem uma cópia
# da chave do projeto em colaborar/chaves/<nome>.enc, cifrada com a senha que
# recebeu do dono (AES-256 + PBKDF2 com 600 mil iterações). A senha é digitada
# só aqui e nunca é gravada; a chave aberta fica num arquivo temporário apagado
# logo após o desbloqueio.

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
passo "1/3  Conferindo ferramentas"

# Executável oficial do git-crypt para Windows, conferido pelo SHA-256 (docs/criptografia.md).
WIN_URL="https://github.com/AGWA/git-crypt/releases/download/0.7.0/git-crypt-0.7.0-x86_64.exe"
WIN_SHA="8c54a3b583cd4fc1483c952480116a9c86f771b02d4403fc6d3627b26cf146e2"

instalar_git_crypt() {
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      destino="$HOME/bin"; mkdir -p "$destino"
      echo "Baixando o git-crypt oficial (GitHub AGWA/git-crypt 0.7.0)..."
      curl -fsSL -o "$destino/git-crypt.exe.tmp" "$WIN_URL" || { vermelho "Falha no download."; return 1; }
      if [ "$(sha256sum "$destino/git-crypt.exe.tmp" | cut -d' ' -f1)" != "$WIN_SHA" ]; then
        rm -f "$destino/git-crypt.exe.tmp"
        vermelho "O arquivo baixado não confere com o SHA-256 esperado. Nada foi instalado."
        return 1
      fi
      mv "$destino/git-crypt.exe.tmp" "$destino/git-crypt.exe"
      export PATH="$destino:$PATH"
      grep -qs 'HOME/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
      ;;
    Darwin)
      command -v brew >/dev/null || {
        vermelho "Falta o Homebrew. Instale pelo comando em https://brew.sh (pede a senha do Mac) e rode de novo."
        return 1
      }
      brew install git-crypt
      ;;
    Linux)
      amarelo "Vai pedir a senha de administrador do Linux para instalar."
      if command -v apt-get >/dev/null; then sudo apt-get install -y git-crypt
      elif command -v dnf >/dev/null; then sudo dnf install -y git-crypt
      elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm git-crypt
      else vermelho "Instale o git-crypt pelo gerenciador de pacotes da sua distribuição."; return 1
      fi
      ;;
    *) vermelho "Sistema não reconhecido. Instale o git-crypt: https://github.com/AGWA/git-crypt"; return 1 ;;
  esac
  command -v git-crypt >/dev/null
}

if ! command -v openssl >/dev/null; then
  vermelho "openssl não encontrado."
  echo "  Windows: instale o Git for Windows (git-scm.com) e rode este script pelo Git Bash."
  echo "  Linux:   sudo apt install openssl"
  exit 1
fi

# Mesma cifra do gerador (scripts/acessos.sh). No Mac, o openssl do sistema é o
# LibreSSL; se ele não suportar estes parâmetros, usa o do Homebrew.
CIFRA=(-aes-256-cbc -pbkdf2 -iter 600000 -md sha256)
OPENSSL=openssl
openssl_ok() {
  local volta
  volta="$(printf 'teste' | "$1" enc -aes-256-cbc -pbkdf2 -iter 1000 -md sha256 -salt -pass pass:teste 2>/dev/null \
    | "$1" enc -d -aes-256-cbc -pbkdf2 -iter 1000 -md sha256 -pass pass:teste 2>/dev/null)" || return 1
  [ "$volta" = "teste" ]
}
if ! openssl_ok "$OPENSSL"; then
  brew_ssl=""
  command -v brew >/dev/null && brew_ssl="$(brew --prefix openssl@3 2>/dev/null)/bin/openssl"
  if [ -n "$brew_ssl" ] && [ -x "$brew_ssl" ] && openssl_ok "$brew_ssl"; then
    OPENSSL="$brew_ssl"
  else
    vermelho "O openssl deste computador ($(openssl version 2>/dev/null)) não suporta a cifra do projeto."
    case "$(uname -s)" in
      Darwin) echo "  Instale um openssl atual com: brew install openssl@3   e rode de novo." ;;
      *)      echo "  Use o Git Bash do Git for Windows (Windows) ou atualize o openssl (Linux)." ;;
    esac
    exit 1
  fi
fi
if ! command -v git-crypt >/dev/null; then
  amarelo "git-crypt não encontrado. Instalando..."
  instalar_git_crypt || { amarelo "Resolva o que apareceu acima e rode de novo."; exit 1; }
fi
verde "openssl e git-crypt instalados."

# Node só é preciso para rodar o projeto, não para abrir o código: aqui só avisa.
node_ok=0
if command -v node >/dev/null; then
  IFS=. read -r maior menor _ <<< "$(node -v | tr -d v)"
  { [ "$maior" -gt 22 ] || { [ "$maior" -eq 22 ] && [ "$menor" -ge 9 ]; }; } && node_ok=1
fi
[ "$node_ok" = 1 ] || amarelo "Aviso: para rodar o MNEME você vai precisar do Node 22.9 ou mais novo (https://nodejs.org, versão LTS)."

# ---------------------------------------------------------------- 2. quem é
passo "2/3  Quem é você"
git pull --quiet 2>/dev/null || true
nomes="$(ls colaborar/chaves/*.enc 2>/dev/null | sed 's#.*/##; s#\.enc$##' | tr '\n' ' ')"
[ -n "$nomes" ] || { vermelho "Nenhum colaborador cadastrado ainda. Fale com o dono do projeto."; exit 1; }
echo "Colaboradores: $nomes"
read -r -p "  Seu nome: " nome
nome="$(printf '%s' "$nome" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
arquivo="colaborar/chaves/$nome.enc"
[ -f "$arquivo" ] || { vermelho "Não há acesso para \"$nome\". Confira o nome ou fale com o dono do projeto."; exit 1; }

# ---------------------------------------------------------------- 3. desbloqueio
passo "3/3  Abrindo o código"
chave="$(mktemp)"
trap 'rm -f "$chave"' EXIT
echo "  Dica: no Git Bash, colar é Shift+Insert ou clique direito (Ctrl+V não cola e estraga a senha)."
for tentativa in 1 2 3; do
  # IFS= mantém a senha exatamente como digitada (sem cortar espaços nas pontas).
  IFS= read -r -s -p "  Senha (não aparece enquanto digita): " senha; echo
  if [[ "$senha" =~ [[:cntrl:]] ]]; then
    vermelho "A senha tem um caractere de controle (provavelmente um Ctrl+V). Digite ou cole com Shift+Insert."
    continue
  fi
  erro="$(printf '%s' "$senha" | "$OPENSSL" enc -d "${CIFRA[@]}" -pass stdin -in "$arquivo" -out "$chave" 2>&1 >/dev/null)" || true
  if [ -s "$chave" ] && head -c 12 "$chave" | grep -q "GITCRYPTKEY"; then
    unset senha
    git-crypt unlock "$chave"
    rm -f "$chave"
    if cifrado; then
      vermelho "Ainda cifrado. Rode de novo ou fale com o dono do projeto."
      exit 1
    fi
    verde "Pronto: código aberto. Commits que você fizer voltam cifrados automaticamente."
    if [ "$node_ok" = 1 ]; then
      echo "Próximo passo: npm install e leia docs/operacao.md."
    else
      echo "Próximo passo: instale o Node 22.9+ (https://nodejs.org), rode npm install e leia docs/operacao.md."
    fi
    exit 0
  fi
  : > "$chave"
  if [ -n "$erro" ] && ! printf '%s' "$erro" | grep -qi "bad decrypt"; then
    vermelho "Erro do openssl (não é a senha): $(printf '%s' "$erro" | head -2 | tr '\n' ' ')"
    amarelo "Mande essa mensagem ao dono do projeto."
    exit 1
  fi
  vermelho "Senha incorreta (você digitou ${#senha} caracteres)."
done
unset senha
amarelo "Três tentativas erradas. Confira com o dono do projeto se a quantidade de caracteres bate,"
amarelo "digite a senha à mão e atenção a letras parecidas: l, I e 1; O e 0."
exit 1
