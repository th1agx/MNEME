# Como colaborar no MNEME

Qualquer colaborador configura o próprio computador (macOS, Linux ou Windows com Git Bash) em três passos. O robô roda na Oracle A1 e não depende de nenhum computador de colaborador.

1. Clone o repositório:

   ```bash
   git clone https://github.com/th1agx/MNEME.git
   ```

2. Crie o arquivo `.env` na raiz do repositório com o bloco do e-mail de chaves que o dono do projeto mandou. O `.env` nunca vai para o Git.
3. Na raiz do repositório, rode:

   ```bash
   bash colaborar/configurar.sh
   ```

O script:

- grava a chave de acesso à Oracle em `~/.ssh/mneme-oracle` e cria o atalho `ssh mneme-a1`;
- instala o `uv` (se faltar) e as dependências do Python, e roda os testes;
- baixa o Knowledge Vault da Oracle para a pasta `vault/` do repositório e agenda a sincronização a cada 10 minutos (launchd no macOS, cron no Linux, Agendador de Tarefas no Windows).

Depois, no Obsidian, escolha **Open folder as vault** e abra a pasta `vault`. As configurações do Obsidian (`vault/.obsidian/`) também são sincronizadas, então todos veem o mesmo Vault.

## Sincronização do Vault

| Arquivo | O que é |
|---|---|
| [sincronizar-vault.sh](sincronizar-vault.sh) | Envia suas edições e traz as da Oracle. Rode à mão quando quiser |
| `~/.mneme/vault.log` | Registro de cada sincronização |
| `~/.mneme/vault-backups/` | Backup diário do Vault deste computador (14 pacotes) |

Se a mesma linha mudar aqui e na Oracle, vale a sua edição, e a versão da Oracle fica no histórico do Git. As regras das notas estão em [docs/VAULT.md](../docs/VAULT.md).

## Para o dono do projeto

[gerar-chaves.sh](gerar-chaves.sh) gera `privado/chaves-colaboradores.md` com o `.env` completo, incluindo a chave de acesso à A1. A pasta `privado/` é ignorada pelo Git. Todos usam a mesma chave da A1: para tirar alguém do projeto, troque a chave na A1, rode o script de novo e mande o arquivo novo para quem continua.
