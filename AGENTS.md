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

Se o código estiver aberto (sem `GITCRYPT`), siga normalmente as convenções descritas em `docs/codigo.md`. Commits voltam cifrados sozinhos; nunca altere `.gitattributes` para liberar arquivos sem pedido explícito do dono do projeto.
