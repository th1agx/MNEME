# Matriz de rastreabilidade

Estado registrado em 12/11/2026. O que está pendente aqui continua no escopo, como define [PRODUCT_CHARTER.md](../PRODUCT_CHARTER.md). Código existente não conta como funcionalidade: uma capacidade só está completa quando seus dados são coletados, guardados, processados e chegam a quem precisa deles. Esta revisão foi feita no checkout local; não comprova estado do serviço ou artefatos remotos.

**Validada** quer dizer que o componente funciona. Não quer dizer que dá lucro.

## Dados e fontes

| Capacidade | Implementada | Rodando | Alimenta o modelo | Validada | Pendente |
|---|---|---|---:|---|---|
| Velas de 1 min (BTC, ETH, SOL), 24 meses | Sim | Sim, ao vivo | **Sim** | Sim: sem lacunas, recuperação testada | Mais ativos |
| Agressão vinda das velas | Sim | Sim | **Sim** | Sim | |
| Funding | Sim | Sim | **Sim** | Parcial | Atualização nos modelos, ao retreinar |
| Trades | Sim | Sim, desde 05/11 | **Não** | Sim: bate com a vela oficial | Atributos, depois de acumular histórico |
| Livro de ofertas | Sim | Sim, desde 05/11 | **Não** | Parcial | Atributos, depois de acumular histórico |
| Open interest | Sim | Sim; histórico de 29 dias | **Não** | Parcial | Atributos |
| Liquidações | Sim | Conectado, sem evento recebido | **Não** | **Não** | Confirmar com evento real |
| Calendário: FOMC | Sim | Sim, 57 reuniões | **Sim** | Sim: datas e fuso conferidos | |
| Calendário: agenda, consenso, resultado, revisões e surpresa | Sim | Sim: lê 7 dias à frente, cada mudança vira versão | **Sim**, família `e_` | Sim: horários conferidos com CPI e FOMC, 30 mil eventos em 24 meses | Termos de uso da fonte (pendência externa) |
| Notícias (Fed, ECB, BEA) | Sim: um ciclo em `mneme.inteligencia`, Hugin e candidatos Munin integrados | **Não confirmado no serviço remoto**; requer implantação e leitura do batimento/Parquet no serviço | **Código ligado**: treino e previsor usam o caminho `n_*` se o manifesto pedir as colunas; artefatos remotos não inspecionados | Testes locais cobrem feed → gate → Parquet → atenção → entrada de modelo simulada. Consulta HTTP pontual local respondeu nas três fontes e admitiu 1 artigo Fed; classificação e ganho preditivo ainda precisam de amostra medida | Validar serviço implantado; acumular amostra; medir classificação e ganho preditivo fora da amostra |
| X (API oficial) | Sim, com teto de gasto | **Não: sem credencial** | **Não** | Só com dados simulados | Credencial e orçamento; tendências |
| Provedor de sinais (traders) | Sim | Sim, na A1 (serviço `traders`), desde 07/11 | **Não** | Parcial: reinício real da A1 testado | Telegram no `.env` da A1 |
| Forex e ouro (EUR/USD, GBP/USD, USD/JPY, XAU/USD), histórico | Sim, 24 meses | Importação manual | **Sim**, no treino do motor | Sim: 1.008 medições, nenhuma acima do empate depois da correção | Termos da fonte |
| Forex e ouro ao vivo | Só no gráfico do TradingView | **Não** no servidor | **Não** | Não | Fonte ao vivo para o motor |
| Motor: decisão, risco, sinal, execução simulada e diário | Sim | Sim, desde 06/11 | Usa os pesos por modalidade | Testes de ponta a ponta; sem histórico ao vivo | Acumular operações; Telegram |
| Solana on-chain, carteiras e DEXs | **Não** | Não | **Não** | Não | No escopo: fonte, dataset e adaptador |

## Conhecimento

| Capacidade | Implementada | Consultada por alguém | Validada | Pendente |
|---|---|---|---|---|
| Biblioteca de metodologias | Sim, um arquivo | **Não** | Referências sem conferência | Ingestão |
| Estudos e setups (`robo/conhecimento/`) | Sim | **Não** | Medidos pelo laboratório | Ingestão |
| RAG, embeddings e busca | Sim: 511 documentos, 3.187 trechos, 12 MB | **Ainda não** pelo fluxo de decisão | Busca: 9 de 12 perguntas com o documento certo; 3 falhas por falta de conteúdo (FVG, Ichimoku, Bollinger + RSI) | Mais fontes; ligar à decisão |
| Fontes externas de conhecimento | Sim: arXiv, ChartSchool, documentos locais | Pela biblioteca | Investopedia e SSRN bloqueados, não contornados | Ampliar o limite de 150 páginas |
| LLM local | Sim: leitor de notícias com contexto assíncrono | Só registrado no diário | Sentimento melhor que a regra em 48 notícias; respostas sobre técnicas falham na conferência | Medir utilidade; corrigir respostas |
| LangGraph | **Não** | Não | Não | Integração |
| Knowledge Vault ([VAULT.md](../VAULT.md)) | Sim | Sim, a cada 10 min, desde 06/11 | Pelo RAG | Testes de ponta a ponta; backup restaurado na A1 e no Mac; sincronização nos dois sentidos e conflito testados em 07/11; reinício real da A1 em 07/11 | Abrir no Obsidian do Mac |

## Técnicas

| Capacidade | Calculada | Chega ao modelo | Acrescenta previsão? |
|---|---|---|---|
| RSI, MACD, Bollinger, ATR, ADX, VWAP, médias | Sim, conferidas com TA-Lib | Sim | É a base "só preço" |
| Estrutura, suporte e resistência, rompimentos, padrões de vela | Sim | Sim | Dentro da base |
| Fibonacci, FVG, Order Block, Ichimoku, linhas de tendência, perfil de volume, varredura, spring, topo e fundo duplos | Sim | Sim | **Não, na medição em conjunto** |
| 7 combinações pedidas, regra a regra | Sim, com cortes fixados antes | Como regra medida | **Não**: 0 de 84 medições passa do empate ou de 50% após a correção; não superam a melhor parte |
| Divergência de RSI | Sim | Só na combinação | Não acrescentou |
| Harmônicos, Volume Spread, ombro-cabeça-ombro, triângulos | **Não** | Não | Não medido |
| Elliott Wave | **Não**: subjetivo | Não | Não testável como está |

## Modelos

| Modelo | Treinado | Em uso | Tipo de resultado | Resultado |
|---|---|---|---|---|
| LightGBM de direção, 15 e 60 min, 3 pares | Sim | **Sim: previsor grava sem operar** | Fora da amostra | AUC de 0,517 a 0,544. Geral abaixo do empate; **20% mais confiantes acima dele em ETH 5 e 15 min e BTC 15 min** (candidato, área selada não aberta) |
| XGBoost e regressão logística | Só nos estudos | Não | Fora da amostra | Equivalentes ao LightGBM |
| Volatilidade | Só nos estudos | Não | Fora da amostra | **R² de 0,46 a 0,72**, de 9% a 21% melhor que a referência |
| Eficiência do movimento (regime) | Só nos estudos | Não | Fora da amostra | Quase nada |
| Meta-rótulo sobre regras de reversão | Só nos estudos | Não | Fora da amostra | Nada significativo depois da correção |

## Fluxo de decisão

| Etapa | Situação |
|---|---|
| Dados, múltiplos tempos, indicadores, padrões | Funciona |
| Consultar metodologias | **Não existe** |
| Notícias e informações externas | Chegam aos modelos como atributos; sem histórico para medir, e **ainda não há decisão** para recebê-las |
| Avaliar evidências com modelos | Funciona para velas, funding e FOMC |
| Decision Engine | **Não existe** |
| Risk Engine | **Não existe**; só limites do robô antigo |
| Signal Engine | **Não existe**; só dicas do robô antigo |
| Paper trading dos novos modelos | **Não existe**; o previsor só grava previsões |

## Origem dos resultados

| Tipo | O que existe |
|---|---|
| Backtest | 54 combinações de setups em opção digital e 54 em spot; nenhuma aprovada |
| Fora da amostra | Modelos com walk-forward, purga e embargo; corte de seleção só com o passado, depois da correção |
| Área selada (desde 01/08/2026) | **Nenhuma hipótese aberta oficialmente**. Estudos anteriores à criação da área tocaram esses meses. **Exposição em 06/11/2026:** o teste visual no TradingView de "Bollinger fora da banda, ETH, 15 min" mostrou 31/08 a 06/11: 52,75% (288 de 546), abaixo do empate de 54,05% e sem custos. Essa hipótese não tem mais área selada limpa; a prova dela passa a ser a carteira simulada ao vivo. O teste visual mostra só o período recente, então vale para qualquer regra colocada no gráfico |
| Ao vivo, sem operar | Previsões gravadas desde 05/11/2026; placar funcionando (cerca de 60 por modelo de 15 min), amostra ainda sem valor estatístico |
| Paper trading dos novos modelos | **Nenhum** |

## Medições que mudaram conclusões

- **Vazamento corrigido:** selecionar os 20% melhores usando todo o período inflava o resultado. Reversão em ETH, 15 min: de **58,53%** com o corte antigo para **54,30%** com o corte só do passado. Parte da queda também vem de usar menos dados, e nenhuma linha fica significativa.
- **Metodologias:** média entre os pares, 15 min, AUC de 0,5341 com metodologias e 0,5345 só com preço. Elas não acrescentaram previsão de direção nessa forma de uso.
- **Direção:** existe sinal acima do acaso, com AUC próximo de 0,53. No geral fica abaixo do que o payout exige.
- **Confiantes (candidato, não aprovado):** com corte só do passado e empate em 54,05%, ETH 15 min dá 57,19% (n = 6.036; intervalo por dias de 55,91% a 58,52%; 6 de 6 trimestres; 56,33% com 1 minuto de atraso). ETH 5 min dá 56,21% e BTC 15 min, 56,19%; os outros seis casos não passam. Sem vazamento ao esconder o futuro em dados reais; rótulo embaralhado cai para 48,88%. 91% desses sinais vão contra os últimos 15 minutos: é principalmente **reversão após movimento forte**. Falta a área selada, o preço e o payout reais da corretora.
- **Combinações:** juntar metodologias não melhorou nenhuma medição. O efeito individual mais estável é RSI extremo, perto de 55% nos três pares, também reversão. Rompimentos acertam só de 43% a 44% (hipótese nova, ainda não testada: operar contra eles).
- **Calendário:** o movimento nos 15 minutos após indicadores americanos é de 14% a 18% maior que no mesmo horário sem evento. A surpresa não previu direção: nenhuma relação significativa após a correção, com poucos eventos (13 CPI, 26 payroll). Somar a agenda à previsão de volatilidade não trouxe ganho demonstrado: de -0,14% a +0,12% no geral, com intervalo incluindo zero. Limite: há só cerca de 200 amostras com evento à frente, no mesmo nível do mínimo por folha do modelo, então esse teste tem pouca força na janela do evento.
- **Fuso corrigido:** o campo de hora da fonte traz UTC-5 fixo, e não GMT. Os eventos ficaram 5 horas adiantados até a correção. Registros `reacao_macro` e `agenda_volatilidade` anteriores ao commit 649f459 não valem.
- **Volatilidade:** é o que os dados preveem melhor. Serve para filtrar momentos, dimensionar risco e escolher quando não operar.
