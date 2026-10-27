# MNEME: criptografia do repositório

## Como funciona

O repositório é público, mas o código e as configurações são criptografados com **git-crypt** (AES-256 em modo CTR, com chave simétrica). A criptografia é transparente: quem tem a chave trabalha normalmente; no GitHub e em clones sem a chave, os arquivos aparecem como binário.

As regras ficam em [`.gitattributes`](../.gitattributes): **tudo é criptografado por padrão** e só o que está listado lá fica aberto (README, `docs/`, `.gitignore`, `.gitattributes`, `LICENSE`, `SECURITY.md`, `.github/`). Um arquivo novo entra criptografado automaticamente; publicar algo exige liberar de propósito.

## Trabalhar no projeto (com a chave)

```bash
git clone https://github.com/th1agx/MNEME.git
cd MNEME
git-crypt unlock /caminho/para/mneme-git-crypt.key
```

Depois do `unlock`, os arquivos aparecem decifrados e todo commit volta a ser cifrado sozinho.

Conferir o que está cifrado:

```bash
git-crypt status -e
```

## Instalar o git-crypt

- **Linux (VPS):** `sudo apt install git-crypt`
- **Windows:** executável oficial em https://github.com/AGWA/git-crypt/releases (versão 0.7.0, `git-crypt-0.7.0-x86_64.exe`, 5.903.509 bytes, SHA-256 `8c54a3b583cd4fc1483c952480116a9c86f771b02d4403fc6d3627b26cf146e2` conferido no download). Coloque numa pasta do `PATH` com o nome `git-crypt.exe`.

## Acesso por colaborador (senha)

Além da chave simétrica (backup do dono), cada colaborador abre o código com uma **senha pessoal** que recebe do dono. Ninguém recebe arquivo de chave.

- Em `colaborar/chaves/<nome>.enc` fica uma cópia da chave do projeto cifrada com a senha daquele colaborador (AES-256-CBC, PBKDF2-SHA256 com 600 mil iterações, via `openssl`). Esses arquivos são públicos: sem a senha, não abrem.
- As senhas são criadas pelo dono e ficam só no `.env` dele (fora do git), uma linha `ACESSO_<NOME>=` por pessoa, com 16 caracteres ou mais: qualquer pessoa pode baixar o `.enc` e tentar senhas sem limite. O dono manda cada senha por um canal privado (WhatsApp, ligação).
- O colaborador roda `bash colaborar/acesso.sh` (Git Bash no Windows). O script confere o `openssl`, instala o `git-crypt` se faltar (Windows: baixa o executável oficial 0.7.0 e confere o SHA-256 abaixo antes de usar; macOS: `brew`; Linux: `apt`, `dnf` ou `pacman`), avisa se falta o Node 22.9+, pergunta o nome, pede a senha sem mostrar na tela, decifra a chave num arquivo temporário, roda `git-crypt unlock` e apaga o temporário.

Assistentes de código (Claude, Codex) leem `CLAUDE.md` e `AGENTS.md`, que ficam abertos: com o código cifrado, eles não editam nada e orientam a pessoa a rodar o script.

Para enviar alterações, o colaborador também precisa ser adicionado no GitHub (*Settings > Collaborators*); só ler não exige isso.

### Dono: adicionar ou trocar um colaborador

Com o código aberto no seu computador, coloque a senha no `.env`:

```bash
ACESSO_NOME=senha-forte-com-16-ou-mais-caracteres
```

Depois gere os arquivos e publique:

```bash
npm run acessos
git add colaborar/chaves && git commit -m "Acessos de colaboradores" && git push
```

O script tira a chave do próprio repositório (`git-crypt export-key`), grava `colaborar/chaves/nome.enc` para cada linha `ACESSO_` e apaga o arquivo de quem saiu do `.env`. O nome (minúsculo) é o que a pessoa digita no `acesso.sh`. Ninguém precisa de GPG: a senha é digitada no terminal.

### Remover um colaborador

Tirar a linha do `.env` e rodar `npm run acessos` apaga o `.enc`, o que impede um clone novo de abrir, mas não revoga: a senha continua abrindo o `.enc` que ficou no histórico, quem já abriu o código continua com o que leu, e a chave antiga abre todos os commits já feitos. Para cortar o acesso daqui para frente, siga a **Rotação** abaixo e gere senhas novas só para quem deve continuar.

O acesso por GPG (`git-crypt add-gpg-user`) continua funcionando para a chave do dono em `.git-crypt/keys/`.

## Gestão da chave

- **Uma chave só, guardada em dois lugares:** gerenciador de senhas (anexo ou texto em base64) e um backup offline. Perder a chave sem nenhuma cópia decifrada em algum computador significa perder o código.
- **Nunca** dentro do repositório, em chat, e-mail ou issue.
- **Quem tem acesso:** só pessoas e máquinas que precisam compilar o projeto (seu computador e a VPS). Ferramentas na nuvem que editam o repositório (ex.: Codex) não conseguem ler o código sem a chave.

## Rotação (se a chave vazar)

A chave antiga continua abrindo **todos os commits feitos com ela**. Trocar a chave protege só o que vier depois. Por isso, num vazamento:

1. Gerar chave nova (`git-crypt init` num histórico novo) e re-cifrar o estado atual.
2. Apagar e recriar o repositório no GitHub com o histórico novo (force push não basta: pull requests antigos mantêm os commits acessíveis).
3. Trocar todos os segredos operacionais por precaução (chaves de API, carteira, Telegram), pois o vazador pode ter lido configurações antigas.

## Limites desta proteção

- Protege a **confidencialidade do código** no GitHub; não protege uma máquina já comprometida que tenha o repositório desbloqueado.
- Nomes de arquivos, tamanhos aproximados e mensagens de commit continuam visíveis. Não coloque detalhes sensíveis nas mensagens de commit.
- Os segredos de operação (`.env`) seguem fora do git, independentemente do git-crypt.
- Histórico: o código ficou público por algum tempo antes desta configuração; o repositório foi recriado do zero para remover os commits antigos, mas cópias feitas nesse período não podem ser recolhidas.
