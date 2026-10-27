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

## Acesso por colaborador (GPG)

Além da chave simétrica (backup do dono), cada colaborador tem acesso pela **própria chave GPG**. O repositório guarda em `.git-crypt/keys/` uma cópia da chave do projeto cifrada para cada colaborador autorizado; só quem tem a chave privada GPG correspondente consegue abrir. Ninguém compartilha arquivo de chave nem senha.

### Colaborador: criar a chave (uma vez, no computador dele)

1. Instalar o GnuPG e o git-crypt: no Windows o `gpg` já vem no Git for Windows (Git Bash) e o git-crypt segue a seção "Instalar o git-crypt"; macOS `brew install gnupg git-crypt`; Linux `sudo apt install gnupg git-crypt`.
2. Gerar a chave. Uma janela pede a senha da chave, que é só dele. Prefira o e-mail `...@users.noreply.github.com` do GitHub para não expor o e-mail pessoal:

```bash
gpg --quick-generate-key "Nome Sobrenome <email>" default default 2y
```

3. Publicar a chave **pública** no GitHub (*Settings > SSH and GPG keys > New GPG key*), colando a saída de:

```bash
gpg --armor --export email
```

4. Mandar ao dono a **impressão digital** por um canal diferente (ligação, mensagem), para confirmar que a chave é mesmo dele:

```bash
gpg --fingerprint email
```

### Dono: autorizar o colaborador

```bash
curl -s https://github.com/USUARIO.gpg | gpg --import
gpg --fingerprint USUARIO_OU_EMAIL      # conferir com a impressão digital recebida
git-crypt add-gpg-user --trusted IMPRESSAO_DIGITAL
git push
```

O `add-gpg-user` cria um commit com a chave do projeto cifrada para o colaborador. Esse arquivo pode ser público: só a chave privada dele abre.

### Colaborador: abrir o código

```bash
git clone https://github.com/th1agx/MNEME.git && cd MNEME
git-crypt unlock          # pede a senha da chave GPG dele
```

Para enviar alterações, ele também precisa ser adicionado como colaborador do repositório no GitHub (*Settings > Collaborators*); só ler não exige isso.

### Remover um colaborador

O git-crypt não revoga acesso: quem já abriu o código continua com o que leu, e a chave antiga abre todos os commits já feitos. Para cortar o acesso daqui para frente, siga a **Rotação** abaixo e autorize de novo só quem deve continuar.

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
