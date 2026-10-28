# Instruções para assistentes de código (Codex, Claude, Copilot e afins)

Este repositório é **cifrado com git-crypt**. Antes de qualquer tarefa, verifique:

```bash
head -c 9 src/main.ts
```

Se a saída contém `GITCRYPT`, o código está cifrado neste computador. Nesse caso:

1. **Não edite, não formate, não "corrija" e não regenere arquivos cifrados.** Eles são binários; qualquer alteração corrompe o conteúdo, e o commit seria inútil para todos.
2. **Não tente adivinhar, reconstruir ou recriar o código** a partir da documentação.
3. Explique ao usuário, em português, que ele precisa de acesso e peça para rodar no terminal (Git Bash no Windows), na pasta do repositório:

   ```bash
   bash colaborar/acesso.sh
   ```

   O script confere as ferramentas, pergunta o nome da pessoa e pede a senha que ela recebeu do dono do projeto; com a senha certa, desbloqueia o código.
4. **Nunca peça, gere, sugira ou digite a senha**, nem peça o arquivo de chave do git-crypt. A senha é digitada só pela pessoa, direto no terminal.
5. Arquivos abertos que podem ser lidos e editados mesmo sem acesso: `README.md`, `docs/`, `colaborar/`, `AGENTS.md`, `CLAUDE.md`, `.gitattributes`, `.gitignore`.

Para publicar o painel no Cloudflare Pages, estes caminhos são exceções públicas intencionais em `.gitattributes`: `public/**`, `functions/**`, `migrations/**`, `wrangler.jsonc` e `scripts/prepare-pages.sh`. O workflow em `.github/workflows/` também é público. O restante continua cifrado por padrão. Nunca coloque credenciais, chaves privadas ou origens privadas nesses caminhos; mantenha o código do bot em `src/` cifrado.

Se o código estiver aberto (sem `GITCRYPT`), siga normalmente as convenções descritas em `docs/codigo.md`. Commits voltam cifrados sozinhos; nunca altere `.gitattributes` para liberar arquivos sem pedido explícito do dono do projeto.

## Sigilo da fonte de sinais

A plataforma de onde vêm o ranking e as operações dos traders, e o fornecedor que a expõe, **não podem ser identificados em lugar nenhum do repositório**. Isso vale para:

- **Tudo o que é visível sem a chave:** `README.md`, `docs/`, `colaborar/`, este arquivo, **mensagens de commit**, **nomes de arquivos e pastas**, nomes de branches, issues e pull requests.
- **O código cifrado também:** nomes de classes, funções, variáveis de ambiente, scripts do `package.json`, comentários, textos da interface, mensagens do Telegram e testes.

Como fazer:

- Chame a fonte de **"provedor de sinais"** (no código, `signals`). O ranking é "o ranking"; os traders são "os traders do Top".
- Endereços (REST e WebSocket) ficam **só no `.env`** (`SIGNALS_REST_URL`, `SIGNALS_WS_URL`), nunca como valor padrão no código, em teste ou em documentação. Nos testes, use domínios fictícios como `api.example`.
- Não copie para o repositório textos, links ou trechos de documentação do fornecedor que o identifiquem.
- Antes de cada commit, rode a varredura e confirme que ela não encontra nada:

  ```bash
  bash scripts/sigilo.sh
  ```

- As redes e serviços de execução e mercado (Solana, Jupiter, DexScreener) podem ser citados: o sigilo é só da fonte de sinais.
