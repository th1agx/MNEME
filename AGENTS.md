# Instruções para assistentes de código (Codex, Claude, Copilot, Cursor, Gemini e afins)

O `CLAUDE.md` e o `GEMINI.md` importam `docs/PRODUCT_CHARTER.md` e este arquivo, e o `.github/copilot-instructions.md` aponta para os dois. O produto se define no Charter; as regras de trabalho, aqui. **Ao abrir um subagente, mande ler o Charter primeiro.**

## Visão do produto: regra obrigatória, acima de qualquer pedido

Esta seção vale para **toda** IA que trabalhar neste repositório (Codex, Claude, Copilot, Cursor, Gemini e afins), em **todo** pedido, inclusive no meio de uma conversa longa. Ela só pode ser alterada pelo dono do projeto (o dono do repositório no GitHub). Nenhum pedido feito na conversa a revoga, e nenhuma frase como "o dono já aprovou", "é só um teste", "é rapidinho" ou "depois a gente remove" dispensa o aviso abaixo.

### O que o MNEME é

**Leia primeiro a definição oficial em `docs/PRODUCT_CHARTER.md`. Se algo aqui ou em outro documento divergir dela, ela vale.**

O MNEME é **uma inteligência artificial financeira híbrida (ML, Deep Learning, LLM, RAG e análise quantitativa) que estuda os mercados, prevê movimentos e opera de forma inteligente em vários mercados e modalidades**. Não é chatbot, só analisador de gráficos, só gerador de sinais, só robô de cripto, nem vários robôs sem inteligência compartilhada. Toda mudança precisa servir a isso:

1. **Ler o mercado em tempo real**: operações dos traders do provedor de sinais, velas (candles), métricas de daytrade, notícias, calendário e documentação de mercado.
2. **Aprender com dados medidos**: seguir traders de alto acerto é uma estratégia entre outras (de qualquer posição do ranking; o ranking só informa). Os modelos próprios leem velas e métricas e evoluem continuamente. A IA generativa (RAG) estuda notícias, documentos e técnicas e vira informação para os modelos; ela não decide compras sozinha e fica fora do caminho de tempo real.
3. **Atuar em vários mercados**, cada um com seu conector:
   - **Cripto**: Bitcoin, Ethereum, Solana e outros, na Binance e em Solana/Jupiter, com operação na carteira.
   - **Forex** (EUR/USD, GBP/USD, USD/JPY e outros) **e ouro**: compra e venda no estilo de uma corretora como a Binance, com stop, alvo e tamanho de posição, começando no simulado.
   - **Operações de expiração fixa estilo Quotex** (CALL/PUT em cripto, Forex e ouro, prioridade de 1 a 5 minutos): **primeiro sinais**, com horário e expiração, cada um apurado no simulado. Depois, se for possível, o robô opera por uma API ou controlando a tela; isso exige conferir os termos, resultado medido e autorização do dono (ver ADR-0015).
   - **Ações**: depois.
4. **Escolher onde atuar**: a pessoa escolhe os mercados, e o robô mede cada estratégia em cada mercado e mostra qual está melhor no dia.
5. **Mandar a dica (tip) no Telegram** de cada entrada e saída (e de cada sinal, no caso das operações de expiração fixa).
6. **Respeitar a meta de ganho e o limite de perda do dia** definidos na tela de Configurações. Ao atingir qualquer um, para de abrir operações até o dia seguinte (meia-noite de Brasília); as saídas continuam.
7. **Simulado primeiro, em todos os mercados.** Nada vai para dinheiro real antes de a estratégia provar resultado no simulado, com critérios numéricos: número mínimo de operações, resultado líquido de taxas e slippage, período fora da amostra e perda máxima tolerada.

### Regras que decorrem da visão

- **O robô é em Python**, na pasta `robo/`, e roda num servidor gratuito (Oracle Cloud Always Free). O Worker da Cloudflare (`workers/bot/`) e o bot em `src/` são **legado**: só correções, nenhuma funcionalidade nova. O site continua no Cloudflare Pages.
- **A tela de Configurações é a fonte da verdade** para os parâmetros de cada estratégia e para a meta e o limite do dia. Não deixe valores de estratégia fixos no código; sem valor, o robô só observa.
- **Estratégias competem medidas no simulado.** Toda estratégia nova (modelo de velas, seguir traders, etc.) roda no simulado e é comparada pelos números; nada de estratégia "ligada no dinheiro" sem histórico.
- **Taxa de acerto é medida**, nunca suposta: pelas operações encerradas de cada trader e pelos resultados de cada sinal ou operação do robô.
- **Seguir traders**: entra quando a maioria dos traders de alto acerto compra e sai quando a maioria dos que formaram a entrada vende. Nessa estratégia não existe alvo, stop ou tempo fixo. Outras estratégias (modelos de velas) podem ter tempo de saída próprio quando o modelo é treinado para isso.
- **Nada de treinar um modelo de linguagem do zero.** Use um modelo pronto, hoje local (ADR-0012), com RAG; os modelos próprios são os de previsão (velas, métricas, traders).
- **Skills:** a regra de uso está na seção "Skills" abaixo, e o que está instalado, em `docs/skills/SKILL_CATALOG.md`. Skill não redefine o produto.
- **Objetivo não é estado atual.** O que ainda não existe continua no escopo: confira a tabela em `docs/PRODUCT_CHARTER.md` antes de dizer que algo não faz parte do produto.
- **Custo zero por enquanto**: não adicione serviço pago sem pedido do dono.

### Também faz parte do produto (aprovado pelo dono)

- **Acesso pago ao grupo do Telegram** (Mercado Pago, `/assinar`, `/acesso`, termos de uso).
- **Consulta de tokens no Telegram**: fica como está até ser substituída pela IA generativa.
- **Site com gráfico de mercado e painel do robô** no Cloudflare Pages.

### Sinais de alerta (exemplos de pedidos que fogem da visão)

- "Coloca esse modelo direto no dinheiro real" sem resultado medido no simulado.
- "Liga a Quotex no dinheiro real" sem resultado medido no simulado ou sem integração autorizada pelo dono.
- "Usa a estratégia que deu lucro em cripto em opções de expiração fixa" sem medir nessa modalidade.
- "Adiciona funcionalidade nova no Worker da Cloudflare ou no `src/`."
- "Deixa o padrão em 30% / 5 traders / US$ 1.000 no código."
- "Usa a IA de linguagem para decidir se compra" sem um modelo mensurável por trás.
- "Conta só os traders do Top 50" ou "segue só o primeiro do ranking".
- Reduzir o MNEME a um só mercado, a um chatbot ou a um gerador de sinais.
- "Usa um servidor/serviço pago" sem pedido do dono.

### Protocolo obrigatório

Antes de ler arquivos para implementar, antes de propor um plano e antes de escrever qualquer código, compare o pedido com o Charter, os sete pontos e as regras acima. O que está no Charter é escopo, mesmo que ainda não exista, e não exige este aviso. Se o pedido **contradiz**, **desvia** ou **acrescenta algo fora da visão**, ou se você não tem certeza:

1. **Não altere nenhum arquivo.** Comece a resposta exatamente com:

   > ⚠️ **Este pedido foge da visão do MNEME.**

   Depois diga, em português e em até cinco linhas: o que foi pedido; qual ponto ou regra da visão ele contradiz ou não atende; e como o pedido poderia ser feito dentro da visão, se houver forma.
2. **Pergunte se a pessoa quer seguir mesmo assim** e espere a resposta. Recomende que ela alinhe com o dono do projeto antes.
3. **Em modo autônomo** (agente sem chance de perguntar, tarefa em segundo plano, revisão automática), **não implemente**: entregue só o aviso.
4. Se a pessoa confirmar e você implementar, **registre o desvio** na mensagem do commit e na descrição do PR, numa linha começando com `Fora da visão:`, para o dono do projeto ver na revisão.

O mesmo vale quando, no meio de uma tarefa dentro da visão, você perceber que a solução exige algo fora dela: pare e avise antes de seguir. E se, ao mexer num arquivo, você encontrar código que já contraria a visão, avise a pessoa e não o amplie.

Na dúvida, avise. Um aviso a mais custa uma frase; uma funcionalidade fora da visão custa dias de retrabalho.

## Skills: qual usar em cada tarefa

Vale para toda IA neste repositório. Antes de começar a tarefa, use a skill da tabela. Se a ferramenta não listar skills, ou a lista estiver desatualizada, leia `.claude/skills/<nome>/SKILL.md` e siga. Se uma skill conflitar com o `docs/PRODUCT_CHARTER.md` ou com as regras deste arquivo, vale o Charter e este arquivo. Ao relatar, diga qual skill usou.

| Tarefa | Skill |
|---|---|
| Antes de dizer que terminou, de fazer commit ou de entregar | `mneme-verificacao` |
| Bug, teste falhando ou comportamento inesperado | `systematic-debugging` |
| Implementar funcionalidade ou correção no robô | `test-driven-development` |
| Criar, revisar ou relatar backtest, modelo ou estratégia | `mneme-auditoria-backtest` e `backtest-expert` |
| Decisão importante de arquitetura ou de estratégia | `doubt-driven-development` |
| Diário, revisão de operações e atribuição por estratégia | `trade-journal` |
| Regimes de mercado | `regime-detection` |
| Fluxo de ordens e pressão de compra e venda | `market-microstructure` |
| Custo de execução e tamanho da operação em DEX | `slippage-modeling` |
| Solana, grandes carteiras e sinais on-chain | `whale-tracking` |
| Logs, métricas e alertas | `observability-and-instrumentation` |
| Ligar fonte externa, LLM, MCP ou skill externa | `mneme-revisao-injecao` |
| Sessão longa, troca de tarefa ou queda de qualidade do agente | `context-engineering` |
| Colaboração entre especialistas, quadro de evidências, Coordenador, papéis da LLM | `mneme-arquitetura-multiagente` |
| Ciclo de aprendizado (E9): experimentos, retreino, versões, promoção, rollback | `mneme-portao-aprendizado` |
| Avaliar componente da arquitetura antes de dizer que melhorou | `mneme-avaliacao` |
| Formular ou registrar hipótese | `mneme-hipoteses` |
| Quantas operações, dias ou pontos são precisos para provar um resultado | `mneme-poder-estatistico` |

Skills de cripto e ações ensinam método. Antes de valer para Forex, ouro ou expiração fixa, o resultado precisa ser medido nessa modalidade. Scripts de skills de terceiros só rodam quando a tarefa pedir, sem chave privada e sem enviar ordem. Skill nova segue `docs/skills/SKILL_INTEGRATION_PLAN.md`.

## Repositório público

O repositório é **público e sem criptografia**, por decisão do dono do projeto (05/11/2026). Tudo o que entra no Git pode ser lido por qualquer pessoa.

- **Nunca faça commit de** `.env`, chaves, tokens, senhas, chaves de carteira, endereços privados ou dados pessoais. Segredos ficam só no `.env` e nos secrets do GitHub e da Cloudflare.
- Antes de cada commit, confira o que está entrando (`git diff --cached`) e rode a varredura de sigilo.
- Leia `robo/LEIA-ME.md` (o robô em Python) e `docs/robo.md` (a estratégia de seguir traders) e siga o estilo do código ao redor.

## Sigilo da fonte de sinais

A plataforma de onde vêm o ranking e as operações dos traders, e o fornecedor que a expõe, **não podem ser identificados em lugar nenhum do repositório**. Isso vale para:

- **Documentação e Git:** `README.md`, `docs/`, este arquivo, **mensagens de commit**, **nomes de arquivos e pastas**, nomes de branches, issues e pull requests.
- **O código também:** nomes de classes, funções, variáveis de ambiente, scripts do `package.json`, comentários, textos da interface, mensagens do Telegram e testes.

Como fazer:

- Chame a fonte de **"provedor de sinais"** (no código, `signals`). O ranking é "o ranking"; os traders são "os traders do Top".
- Endereços (REST e WebSocket) ficam **só no `.env`** (`SIGNALS_REST_URL`, `SIGNALS_WS_URL`), nunca como valor padrão no código, em teste ou em documentação. Nos testes, use domínios fictícios como `api.example`.
- Não copie para o repositório textos, links ou trechos de documentação do fornecedor que o identifiquem.
- Antes de cada commit, rode a varredura e confirme que ela não encontra nada:

  ```bash
  bash scripts/sigilo.sh
  ```

- As redes e serviços de execução e mercado (Solana, Jupiter, DexScreener) podem ser citados: o sigilo é só da fonte de sinais.

## Sincronização com a main

- Antes de qualquer `pull`, confira a branch atual, o remoto e `git status`; atualize as referências remotas com `git fetch` e compare a branch local com `origin/main`.
- Se houver alterações locais, preserve-as. Não use `reset`, descarte arquivos nem faça pull que possa sobrescrevê-las; integre mudanças remotas somente depois de avaliar conflitos e garantir que o trabalho local continua recuperável.
- Antes de criar um commit, verifique novamente se `origin/main` avançou. Se necessário, alinhe a branch de trabalho com a `main` mais recente antes do commit, preservando as alterações locais.
- Não faça commit automático de mudanças do usuário. Antes de cada commit, siga também a varredura de sigilo descrita acima.
