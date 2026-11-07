# Roadmap

**Situação:** referência de arquitetura, subordinada ao [Product Charter](../PRODUCT_CHARTER.md). O estado real está em [RASTREABILIDADE.md](RASTREABILIDADE.md). Sem datas prometidas: o tamanho é relativo (P, M, G), e cada fase termina por critério objetivo. As fases entregam valor sozinhas, e pode-se parar em qualquer uma.

## Ordem de implementação

Definida pelo dono em 05/11/2026: construir, testar, medir e evoluir. Esta ordem manda sobre as fases abaixo, que ficam como referência de conteúdo. O roadmap define prioridades e etapas, e não redefine o produto: o objetivo está no [Product Charter](../PRODUCT_CHARTER.md). Um mercado ou capacidade sem fase aqui continua no escopo.

| Entrega | O que funciona ao final | Critério |
|---|---|---|
| **E1** | Velas históricas e ao vivo, indicadores, tendência e padrões | Indicadores batem com o TA-Lib; nada olha o futuro; coleta recupera lacunas |
| **E2** | Coleta de trades, livro, funding e open interest | Rodando na A1, com tamanho diário medido |
| **E3** | Backtest e validação com purga e embargo; estudos refeitos | Dado embaralhado resulta em cerca de 50% |
| **E4** | LightGBM e XGBoost treinados com histórico; registro de experimentos | Comparados a referências simples, depois de custos |
| **E5** | Decision Engine, Risk Engine e paper trading por estratégia | Nenhuma sequência ultrapassa os limites |
| **E6** | Sinais com ciclo de vida, Telegram e avaliação | Todo sinal tem estado e resultado |
| **E7** | Knowledge Engine com RAG | Responde com fontes e resultados medidos |
| **E8** | Notícias e calendário, com Ollama e LangGraph | Coleta e sinais continuam com o LLM parado |
| **E9** | Ciclo de aprendizado: hipótese, experimento e comparação | Uma hipótese percorre o ciclo sozinha, até a aprovação |
| **E10** | Execução real controlada | Só com aprovação explícita do dono |

## Estado real em 07/11/2026

Execução permanente na Oracle A1 (Docker Compose, `restart: always`, health check por batimento). O Mac é só desenvolvimento e administração, e o Obsidian é a interface do Knowledge Vault. "Feito" exige evidência, não só código.

| Entrega | Estado | Evidência | Bloqueio ou próximo passo |
|---|---|---|---|
| **E1** | Feito | Velas de 24 meses e ao vivo; indicadores conferidos com o TA-Lib | Mais ativos |
| **E2** | Rodando | Trades, livro, funding e OI na A1 desde 05/11; após o reinício de 07/11 o serviço `fluxo` travava (imagem de 05/11 sem `resultados_macro`): imagem refeita, 0 reinícios | Medir o tamanho diário; virar atributo depois de acumular |
| **E3** | Feito | Estudos refeitos com purga, embargo, placebo e correção de Holm (05/11) | |
| **E4** | Feito, sem vantagem | LightGBM grava previsões sem operar; AUC de 0,517 a 0,544 | Área selada do candidato "20% mais confiantes" |
| **E5** | Acumulando | Motor desde 06/11: cerca de 200 operadas e encerradas em expiração fixa, 62,2% de acerto (120 ganhos, 73 perdas, 7 empates), pior sequência de 7 perdas, drawdown de 7,15 numa banca de 100; 1.106 em sombra (59,1%) | Amostra pequena e de 2 dias: não prova vantagem. Mínimo de evidência configurado: 200 por estratégia |
| **E6** | Parcial | Robô de traders na A1 com o Telegram (`@mneme_br_bot`, grupo MNEME) conferido por `getMe` e `getChat`. Fluxo sinal → registro → envio → resultado testado com o Telegram simulado (585 testes). Falha do Telegram (sem rede, erro 502, erro inesperado) não para o robô e deixa a dica na fila. Token e chaves trocados por `***` nos logs; varredura nos 9 serviços, nos logs do Vault e no journal da A1: 0 ocorrências | **Envio real ao grupo ainda não feito** (precisa de autorização para a mensagem de teste, ou de uma entrada real). **Os sinais do motor (CALL/PUT e com stop) não vão ao Telegram**: decidir quais modalidades publicar e com que critério (hoje são ~140 por dia, sem vantagem comprovada) |
| **E7** | Funciona, sem ligação com a decisão | Biblioteca com 1.002 documentos, incluindo o Vault; a busca achou uma nota nova do Vault em 07/11 | Ligar o contexto à decisão com origem e validade gravadas |
| **E8** | Rodando | Notícias e calendário na A1; leitor de LLM grava contexto assíncrono | LangGraph; medir se o contexto melhora a decisão |
| **E9** | Primeiro incremento rodando | `mneme.aprendizado`: hipótese num vocabulário fechado (setup + filtro + par + tempo), teste contra o mesmo setup sem filtro, placebo, 1 min de atraso, Holm sobre todas as hipóteses; resultado vira nota no Vault. Roda de hora em hora na A1 (cron, prioridade mínima). 3 hipóteses testadas em 07/11, todas rejeitadas; a LLM propôs uma repetida e o ciclo usou a enumeração | A LLM ainda não estuda o Vault nem as operações; próxima etapa: hipóteses sobre as operações do motor e uso das notas como contexto |
| **E10** | Bloqueado | | Só com vantagem estatística, validação fora da amostra e aprovação do dono |

Também no escopo oficial, sem entrega concluída: TradingView com a leitura do MNEME, Quotex (sinais primeiro), Forex e ouro ao vivo, Solana on-chain.

### Decisões que dependem do dono

**Modelo da LLM local**, medido em 48 notícias rotuladas (A1, sem GPU):

| Medida | Regra fixa | `qwen3:1.7b` (em uso) | `qwen2.5:3b` |
|---|---:|---:|---:|
| Tipo da informação | 70,8% | 68,8% | 43,8% |
| Sentimento | 64,6% | 75,0% | 83,3% |
| Notícia relevante: precisão / revocação | 55% / 76% | 44% / 100% | 100% / 29% |
| Ativos citados | 76,0% | 28,1% | 69,1% |
| Evidência literal conferida | | 97,9% | 45,8% |
| Segundos por notícia | 0 | 35 | 29 |
| Perguntas sobre técnicas respondidas certo | | 0 de 8 | 0 de 8 |

Recomendação: manter o `qwen3:1.7b` para leitura de notícias, porque é o único com evidência quase sempre conferível, e manter a regra fixa para ativos e tipo. Nenhum dos dois serve para responder sobre técnicas: o E7 precisa melhorar o conteúdo e a busca antes de trocar de modelo. Um modelo maior não cabe com folga na memória da A1 junto com o resto.

**Limites de risco do simulado** (`dados/operacao.json` na A1). Os valores atuais não foram decididos pelo dono:

| Limite | Valor atual | Medido no motor (2 dias) | Observação |
|---|---:|---:|---|
| Meta do dia | 20% | | Muito acima do que a amostra sustenta |
| Perda do dia | 10% | Pior drawdown: 7,15% | |
| Operações por dia | 200 | 62 e 140 | |
| Operações simultâneas | 100 | | |
| Perdas seguidas | 8 | Pior sequência: 7 | Quase disparou |
| Drawdown máximo | 40% | 7,15% | |
| Risco por operação | 1% da banca | | |

Recomendação: decidir os limites por mercado antes de qualquer sinal público do motor, partindo da pior sequência e do pior drawdown medidos ao longo de pelo menos 30 dias. O simulado não arrisca dinheiro, então os valores atuais podem seguir enquanto a amostra cresce.

## Dependências

```mermaid
flowchart TD
    F0[0 Fundação] --> F1[1 Dados]
    F0 --> F3[3 Risco e sinais]
    F1 --> F2[2 Laboratório]
    F2 --> F3
    F1 --> F4[4 Conhecimento]
    F4 --> F5[5 Notícias e calendário]
    F2 --> F5
    F2 --> F6[6 Modelos]
    F5 --> F6
    F3 --> F7[7 Orquestração]
    F5 --> F7
    F3 --> F8[8 Solana real]
    F6 --> F8
    F8 --> F9[9 Binance Spot real]
    F6 --> F10[10 Deep learning e RL]
```

## Fases

### Fase 0: Fundação (P)

Tornar seguro o que já roda.

- Passar o robô do Mac para a A1, em Docker Compose com limites, com trava de instância.
- Backup diário, com restauração testada; monitor de recursos e vigia na Micro.
- Corrigir a autenticação de Configurações e preencher os limites do simulado.
- Atualizar `README.md` e `docs/robo.md`.
- Rodar testes Python no CI.

**Pronto quando:** o robô roda na A1 por 7 dias sem intervenção; uma restauração funciona; o `PUT` sem autenticação é recusado.

### Fase 1: Dados (M)

- Contratos Pydantic e Postgres.
- Migração do SQLite, sem perder o placar ao vivo.
- Coletores de trades, livro, funding, open interest, BCB, Fed.
- Log bruto em Parquet, validação, consulta "como de T".
- Registro da decisão.

**Pronto quando:** 30 dias de coleta com lacunas conhecidas e medidas; tamanho diário medido; teste de vazamento passando; uma decisão passada pode ser reconstruída.

### Fase 2: Laboratório (M)

- Backtest com custo por mercado, atraso e carteira por estratégia.
- Validação com purga e embargo; registro de todas as tentativas; DSR e PBO.
- **Refazer os estudos atuais com o método novo**, corrigindo o acerto dos traders, o viés de sobrevivência e o preço de entrada.

**Pronto quando:** os nove setups e o estudo de velas foram refeitos, com o resultado publicado em `conhecimento/`, mesmo que seja pior; o teste que embaralha o futuro dá cerca de 50%.

### Fase 3: Risco e sinais (M)

- Risk Engine com todos os limites do simulado.
- Kill switch e circuit breaker.
- Sinal com ciclo de vida, três modos e avaliação automática.
- Fluxo de confirmação no Telegram.
- Promoção por nível.

**Pronto quando:** testes de propriedade passam; kill switch testado; todo sinal tem estado e resultado; nenhum sinal sem probabilidade calibrada mostra %.

**Primeira entrega visível de valor:** sinais auditáveis no simulado.

### Fase 4: Conhecimento (P/M)

- Ingestão, pgvector, busca híbrida, catálogo de hipóteses.
- Pesquisa inicial por áreas, ligada aos testes.

**Pronto quando:** a consulta do exemplo responde com fontes e resultados medidos; em um conjunto de perguntas de teste, a busca atinge o patamar combinado de qualidade.

### Fase 5: Notícias e calendário (M)

- Ollama sob demanda, com o modelo escolhido por medição.
- Coleta com limites, deduplicação, classificação e tipos de informação.
- Calendário econômico por fontes permitidas, com surpresa medida.
- Estudo de eventos e placar de precificação.
- Eventos como atributos e como aviso, sem operação.

**Pronto quando:** classificação medida em centenas de notícias rotuladas; estudo de eventos publicado para pelo menos 3 tipos de evento; o caminho rápido não atrasa enquanto o LLM roda.

### Fase 6: Modelos (G)

- Datasets versionados; meta-labeling sobre seguir traders.
- LightGBM por mercado; volatilidade e regime; calibração; registro; drift.
- Comparação com referências simples.

**Pronto quando:** um modelo supera a referência depois de custos e da correção, no nível 2, **ou** um relatório mostra que nenhum superou. As duas conclusões encerram a fase.

### Fase 7: Orquestração (M)

- LangGraph para evento de notícia, estudo diário, ingestão e revisão.
- Checkpoints, tempos limite, fila e limite de uso do LLM.

**Pronto quando:** cada agente tem métrica; derrubar o LLM não afeta o caminho rápido; reinício retoma sem repetir chamadas.

### Fase 8: Solana com capital real (M)

- Portar o executor, com reconciliação.
- Testes de falha e uso do menor valor possível.

**Pronto quando:** todos os itens de "Antes do capital real" estão concluídos, e a diferença entre real e simulado foi medida ao longo de pelo menos 50 operações.

### Fase 9: Binance Spot com capital real (M)

- Executor, testnet e capital mínimo.

**Pronto quando:** os mesmos critérios da fase 8, com chave sem saque.

### Fase 10: Deep learning e RL (G, opcional)

- Só se houver dados e um simulador validado.
- Deve superar o LightGBM com folga, fora da amostra.

**Pronto quando:** houver relatório comparativo, adotando ou descartando.

## Prioridades

1. **Fase 0** primeiro: há riscos abertos hoje, inclusive sem dinheiro real.
2. **Dados crescem antes de modelos:** cada dia não coletado de fluxo é perdido para sempre, enquanto modelos podem esperar. Por isso a fase 1 vem logo depois.
3. **Risco antes de execução.**
4. **Se a vantagem não aparecer na fase 6, não se avança para capital real.** Essa é a saída prevista, e não um fracasso do projeto.

## O que este roadmap não promete

Não promete lucro, nem que algum modelo passará. O curto prazo é quase aleatório, conforme os estudos internos. O roadmap garante um processo para descobrir o que funciona, gastando o mínimo possível para descobrir o que não funciona.

## Próximas decisões do dono

1. Aprovar este roadmap e os critérios de promoção.
3. Confirmar o modelo local, depois de ver as medições.
4. Definir os limites de risco por mercado.
5. Autorizar o uso de créditos do provedor na A1.
