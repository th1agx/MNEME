# Experimentos BTCUSDT M15 no TradingView

Para todas as familias juntas, com entrada somente quando pelo menos duas concordam, use [a estrategia de confluencia](CONFLUENCIA-BTC-M15.md). O script individual abaixo continua disponivel para comparar regras separadamente.

Arquivo: [mneme_btc_m15.pine](mneme_btc_m15.pine), Pine Script v6. Um script com seis regras selecionaveis; cada copia no grafico executa uma regra e tem sua propria carteira simulada. Nao soma as carteiras, nao escolhe automaticamente a melhor estrategia e nao envia ordens ao MNEME ou a corretoras.

## Como iniciar

1. No proprio TradingView, abra **BINANCE:BTCUSDT**, intervalo **15 minutos**, com velas convencionais. Para outra bolsa, mantenha BTCUSDT e registre a bolsa na comparacao. O widget do site MNEME nao executa Pine personalizado.
2. Abra o **Editor Pine**, crie uma estrategia e substitua o conteudo pelo arquivo. Salve e clique em **Adicionar ao grafico**.
3. Nas configuracoes do script, escolha a estrategia. Revise periodos, stop, alvo, tempo e inicio. Em **Propriedades**, confira capital, tamanho, comissao e slippage. Marque **Habilitar simulacao** depois dessa revisao.
4. Adicione outras copias e escolha uma regra diferente em cada uma, se o limite de scripts do seu plano permitir. O Testador mostra um relatorio por vez: selecione a copia correspondente. Alternativamente, use uma copia e alterne a regra, exportando cada resultado antes da troca.
5. Mantenha o mesmo inicio, bolsa, capital, tamanho e custos para comparar. Escolha um inicio comum futuro, anote os parametros antes dele e acompanhe as velas novas. Alterar parametros recalcula o passado: isso vira um novo experimento.

O script comeca **pausado**. O inicio padrao e 07/11/2026 00:00 UTC e nao aceita data anterior: preserva o historico selado do laboratorio, iniciado em 01/08/2026. Usa barras anteriores somente para aquecer indicadores; nao gera operacoes anteriores ao inicio. Nao espere operacoes em todas as velas. Nao foi feita simulacao historica nem medicao de lucro para escolher estes parametros.

## Regras de entrada

| Selecao | Compra | Short opcional |
|---|---|---|
| EMA | EMA rapida cruza acima da lenta | Cruza abaixo |
| MACD | Linha MACD cruza acima do sinal | Cruza abaixo |
| RSI | RSI sai da sobrevenda, cruzando o limite inferior para cima | Sai da sobrecompra para baixo |
| Bollinger | Fechamento cruza de volta acima da banda inferior | Cruza de volta abaixo da banda superior |
| Donchian | Fechamento cruza acima da maxima das N velas anteriores | Cruza abaixo da minima anterior |
| Engolfo | Corpo de alta engloba o corpo anterior de baixa | Corpo de baixa engloba o anterior de alta |

As seis regras sao hipoteses independentes. Nao reutilizam os pesos de confluencia M5 existentes. Seus resultados nao representam desempenho do modelo Python.

## Execucao e custos

- Sinal com vela M15 fechada; ordem de mercado preenchida pelo emulador na abertura seguinte. Sem calculo a cada tick ou recalculo apos preenchimento.
- Uma posicao por copia, sem piramidar nem inverter no sinal contrario. No modo long-only, sinal de venda nao abre short nem fecha long: valem as saidas abaixo.
- Stop = ATR da vela do sinal vezes o multiplo configurado, arredondado para ticks. Alvo = distancia desse stop vezes a relacao configurada. As distancias ficam congeladas e sao aplicadas ao preco de preenchimento. O bracket e enviado junto da entrada, podendo sair na mesma vela de entrada.
- Saida adicional pelo numero maximo de velas. Uma vela significa sair na abertura posterior a vela de entrada. Stops podem ter preenchimentos piores em gaps.
- Valores iniciais **ilustrativos**: capital USD 10.000, posicao de 10% do patrimonio, comissao de 0,1% por preenchimento e slippage de 10 ticks por ordem de mercado/stop. Slippage em ticks nao e percentual; ajuste ao tick e ao mercado usados. Tamanho da posicao nao e percentual de risco no stop.
- Padrao long-only para spot. Short e hipotese de derivativo: para mede-lo corretamente, use dados do contrato correto em outro experimento. Este script exige ticker BTCUSDT e nao aceita automaticamente contratos com outro ticker. Funding, emprestimo, liquidacao e spread variavel nao sao modelados.
- O emulador infere o caminho intrabar pelos OHLC quando nao ha dados menores. Se stop e alvo cabem na mesma vela, revise com Bar Magnifier quando disponivel; registre essa configuracao. Os graficos de stop/alvo so atualizam no fechamento, mas as ordens bracket ja estao no emulador.

## Comparacao sem escolher pelo acaso

Registre cada tentativa, inclusive perdas, e nao apenas a vencedora. Exporte a lista de operacoes de cada copia e anote: identificador, regra, parametros, bolsa, intervalo observado, capital, tamanho, custos, numero de trades, resultado liquido, drawdown maximo, profit factor e tempo em posicao. O historico disponivel e o numero de copias dependem do plano do TradingView; nao foi contratado nenhum servico.

Reserve um periodo futuro sem ajustes para validar a candidata e repita com custos e atraso maiores. Compare tambem com manter BTC no mesmo periodo. Taxa de acerto ou lucro de poucas operacoes nao aprova estrategia; muitas combinacoes aumentam a chance de uma vencedora por acaso. Antes de integrar ao robo, registre os resultados no laboratorio existente e aplique sua auditoria fora da amostra, incluindo correcao por multiplos testes. Estas copias nao leem as Configuracoes do site nem os controles diarios do robo Python; sao experimentos isolados do emulador.

## Estado de verificacao

Em 07/11/2026, apos login, o codigo foi compilado e adicionado a BINANCE:BTCUSDT M15 no TradingView. A fonte copiada de volta do editor foi comparada integralmente ao texto inserido. Propriedades conferidas: USD 10.000, 10% do patrimonio por entrada, comissao de 0,1%, slippage de 10 ticks, sem alavancagem, execucao no fechamento e preenchimento no proximo tick. Simulacao habilitada; seletor das seis regras conferido. EMA nao apresentou operacoes no intervalo curto observado. Ao selecionar Engolfo, a lista mostrou uma entrada long simulada ainda aberta, confirmando o fluxo de entrada e exibicao do bracket. Preenchimento das saidas e as outras quatro regras nao foram verificados individualmente. Esta observacao funcional nao valida rentabilidade.

A conta Basic informou limite de um script salvo ja atingido. A copia aberta no grafico ficou em Engolfo, sem salvar na biblioteca; nenhum script existente foi substituido e nenhum plano pago foi contratado. Mantenha o arquivo local, pois a copia nao salva pode se perder ao fechar ou recarregar a pagina. Nao foram deixadas seis simulacoes simultaneas nem um robo autonomo na nuvem.

A suite Python local nao rodou: `python -m pytest` retornou `No module named pytest`; nao houve execucao na A1. Nenhuma mudanca foi feita no motor Python. As alteracoes locais nao foram commitadas nem publicadas.

Referencias oficiais: [estrategias e emulador](https://www.tradingview.com/pine-script-docs/concepts/strategies/), [ordens de saida em ticks](https://www.tradingview.com/pine-script-docs/faq/strategies/), [limites dos widgets](https://www.tradingview.com/widget-docs/faq/general/).
