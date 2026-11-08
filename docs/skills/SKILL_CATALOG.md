# Catálogo de skills do MNEME

Biblioteca do agente de desenvolvimento e pesquisa. Skills não fazem parte da arquitetura operacional e não redefinem o produto, que está no [Product Charter](../PRODUCT_CHARTER.md). Se uma skill conflitar com o Charter, vale o Charter.

Todas ficam em `.claude/skills/`. Scripts de terceiros só rodam quando alguém pede, e nenhum gancho roda sozinho.

## Originais da comunidade

Instaladas sem mudança no texto, com `LICENSE` e `ORIGEM.txt` na pasta.

| Skill | Autor | Licença | Quando usar |
|---|---|---|---|
| `systematic-debugging` | Jesse Vincent (`obra/superpowers`) | MIT | Antes de propor correção para falha ou bug |
| `test-driven-development` | Jesse Vincent (`obra/superpowers`) | MIT | Ao implementar funcionalidade ou correção |
| `context-engineering` | Addy Osmani (`addyosmani/agent-skills`) | MIT | Quando a qualidade do agente cair ou ao trocar de tarefa |
| `doubt-driven-development` | Addy Osmani (`addyosmani/agent-skills`) | MIT | Em decisões importantes que precisam de revisão crítica |
| `observability-and-instrumentation` | Addy Osmani (`addyosmani/agent-skills`) | MIT | Ao adicionar logs, métricas ou alertas ao robô |
| `backtest-expert` | TraderMonty (`tradermonty/claude-trading-skills`) | MIT | Ao testar a robustez de estratégias |
| `market-microstructure` | agiprolabs (`agiprolabs/claude-trading-skills`) | MIT | Fluxo de ordens e pressão de compra e venda em DEX |
| `regime-detection` | agiprolabs (`agiprolabs/claude-trading-skills`) | MIT | Identificar regimes de mercado |
| `slippage-modeling` | agiprolabs (`agiprolabs/claude-trading-skills`) | MIT | Estimar custo de execução e tamanho da operação em AMM |
| `whale-tracking` | agiprolabs (`agiprolabs/claude-trading-skills`) | MIT | Grandes carteiras e sinais on-chain em Solana |
| `trade-journal` | agiprolabs (`agiprolabs/claude-trading-skills`) | MIT | Diário, revisão de desempenho e atribuição por estratégia |

## Feitas para o MNEME

| Skill | Quando usar | Inspirada em |
|---|---|---|
| `mneme-verificacao` | Antes de dizer que terminou, de fazer commit ou de entregar | `obra/superpowers` |
| `mneme-auditoria-backtest` | Ao criar, revisar ou relatar backtest, modelo ou estratégia | `agiprolabs/claude-trading-skills` e ideias públicas |
| `mneme-revisao-injecao` | Ao ligar fonte externa, LLM, MCP ou skill externa | `basitalisandhu/agent-security-skills` |
| `mneme-arquitetura-multiagente` | Ao desenhar ou mudar a colaboração entre especialistas, o quadro de evidências e o Coordenador | `muratcankoylan/Agent-Skills-for-Context-Engineering` (multi-agent-patterns) e `magnus919/agent-skills` (multi-agent-coordination), MIT |
| `mneme-portao-aprendizado` | Ao construir o ciclo de aprendizado: experimentos, retreino, versões, promoção e rollback | `muratcankoylan/Agent-Skills-for-Context-Engineering` (harness-engineering), MIT |
| `mneme-avaliacao` | Antes de dizer que um componente da arquitetura melhorou | `muratcankoylan/Agent-Skills-for-Context-Engineering` (evaluation), MIT |
| `mneme-hipoteses` | Ao formular ou registrar hipóteses do E9 e dos estudos | `K-Dense-AI/claude-scientific-skills` (hypothesis-generation), MIT |
| `mneme-poder-estatistico` | Para saber quantas operações, dias ou pontos são precisos para provar um resultado | `K-Dense-AI/claude-scientific-skills` (statistical-power), MIT |

As cinco acima são adaptações. Como toda skill `mneme-*`, a pasta tem só o `SKILL.md`, com a seção de crédito; a origem detalhada (versão, commit ou impressão do arquivo lido, o que foi aproveitado, adaptado e removido) e os avisos de licença MIT das fontes ficam em [`docs/skills/origens/`](origens/). Nenhum script de terceiros foi copiado.

As skills `frontend-design` e `power` já existiam, tratam só de design visual e continuam fora do Git.

## Próximas candidatas

| Candidata | Repositório | Ajudaria em |
|---|---|---|
| `edge-candidate-agent` | `tradermonty/claude-trading-skills` | Ciclo de hipóteses |
| `pine-backtester` | `JerryLiu369/awesome-quant-skills`, procurando o autor original | Scripts do TradingView |
| `helius-api`, `wallet-profiling`, `feature-engineering`, `risk-management` | `agiprolabs/claude-trading-skills` | Solana, atributos e risco |
| `prompt-injection-review`, `mcp-server-review` | `basitalisandhu/agent-security-skills` | Segurança de agentes, na versão original |
| `supply-chain-risk-auditor` | `trailofbits/skills` | Auditar dependências |
| Graphify | `Graphify-Labs/graphify` | Reduzir o gasto de contexto |

A avaliação está em [SKILL_EVALUATION.md](SKILL_EVALUATION.md).
