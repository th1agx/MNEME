# Confluencia tecnica BTCUSDT M15

## Experimento V2: filtro de custos nas proximas entradas

O filtro e aplicado a decisoes no fechamento a partir de **07/11/2026 19:45 UTC (16:45 Brasilia)**, por input. A vela 19:30–19:45 ja precisa passar pelo filtro para enviar entrada para a abertura 19:45. Antes desse corte, a logica de entrada permanece a da V1; saldo, limites diarios e posicao carregada continuam, sem recomecar a carteira. Atualizar o Pine sempre recalcula a simulacao: preenchimentos historicos reconstruidos podem diferir dos observados ao vivo. A referencia confiavel e a copia/captura anterior, nao uma promessa de manter os mesmos resultados dentro do Testador. Saidas de posicoes anteriores seguem por stop, alvo ou tempo. Se o inicio do experimento for posterior ao corte, todas as suas entradas usam V2. As tecnicas e seus votos nao foram alterados nesta etapa: separar regimes e medir confirmacoes correlacionadas ficam para outro experimento.

A estimativa e por unidade de BTC, em USDT. Usa o fechamento do sinal mais o slippage de entrada na direcao da ordem. Calcula taxas de entrada e saida, usando o maior preco entre saida no alvo limite e preenchimento do stop ja com slippage adverso, para reservar o custo de comissao mais conservador. Adiciona reserva de slippage nas duas pontas, inclusive para alvo limite. Com distancias `alvo` e `stop` congeladas no ATR, exige:

- alvo bruto maior que o custo e pelo menos **2 vezes o custo estimado** (folga editavel);
- `(alvo - custo) / (stop + custo)` de pelo menos **1** (minimo editavel);
- precos, distancias e custos validos, alem de todos os controles anteriores.

Esses limites sao hipoteses iniciais, nao parametros escolhidos para fazer as seis perdas das sete operacoes encerradas desaparecerem. Nao ajustam a taxa a zero, nao afastam o alvo para aprovar artificialmente a entrada e nao garantem lucro. Alterar corte, folga ou relacao minima cria uma configuracao experimental diferente: registre os inputs e nao misture seus resultados. A relacao e um cenario de alvo versus stop, **nao expectativa estatistica**: nao considera probabilidade de acerto, funding, gaps, mudancas no spread ou saidas por tempo. O preco real da abertura seguinte ainda e desconhecido; a estimativa pode diferir do preenchimento.

Pine nao expoe a comissao/slippage das Propriedades para esta conta do filtro. Os inputs separados comecam em **0,1% por preenchimento e 10 ticks por ponta**, iguais aos defaults do emulador; a caixa **Taxa e slippage abaixo conferidos com Propriedades** comeca desmarcada. Sem confirma-la, novas entradas apos o corte ficam bloqueadas. Se alterar os custos em Propriedades, atualize tambem esses inputs e confira novamente. Os custos do emulador permanecem cobrados normalmente.

O painel distingue **V1 ate corte de custos** de **V2 custos**, mostra o custo em USDT por BTC (nao o custo monetario da posicao), a relacao liquida e os bloqueios. Cada sinal candidato bloqueado recebe etiqueta laranja. **Ordens V2** conta ordens de entrada enviadas, nao operacoes encerradas; **bloqueios** conta candles candidatos vetados, podendo repetir a mesma oportunidade em candles diferentes. Esses contadores sao recalculados a partir do historico carregado, nao constituem um diario persistente.

A referencia anterior foi preservada localmente fora do repositorio, com codigo, captura e transcricao da lista: sete encerradas e uma short aberta as 16:24 Brasilia. A exportacao CSV exigiu plano pago; nao foi contratado. O teste [teste_custos.pine](teste_custos.pine) chama o bloco real BEGIN/END CUSTOS e cobre 15 cenarios de custo/risco, mais cinco do corte temporal. Inclui o limite exato de R numa venda, com comissao do stop apos slippage. Validar resultados futuros separadamente das entradas V1; o total combinado do Testador continua incluindo o historico anterior.

Verificacao V2 em 07/11/2026, aproximadamente 16:34 Brasilia: teste RED acusou funcao ausente antes da implementacao; teste GREEN mostrou **PASSOU: custos (15) + corte temporal (5)**. A estrategia final compilou sem erro observado, e o texto copiado do editor coincidiu com o arquivo instalado. Custos das Propriedades e do filtro conferidos: 0,1% e 10 ticks. Simulacao e confirmacao de custos ativadas, corte 16:45, folga2 e Rmin1, 27 familias habilitadas. Layout confirmou **All changes saved**. Sete operacoes encerradas e uma short aberta continuaram listadas, com os oito precos de entrada preservados. Entretanto, o preenchimento da operacao7 mudou de14:38/75858.51 para14:30/75851.19 na reconstrucao; nao sao resultados historicos identicos. Contadores V2 e bloqueios ainda estavam em zero antes do corte. O filtro nao teve resultado futuro medido nesta verificacao.

Revisao adversarial do segundo modelo identificou e motivou correcoes no relogio do corte (`time_close`), no inicio posterior ao corte, nos pisos de configuracao e na comissao do preenchimento de stop short com slippage. A suite Python local segue indisponivel por falta de pytest; o motor Python nao foi alterado. Nenhum commit ou push foi feito e `scripts/sigilo.sh` esta ausente nesta copia.

Script: [mneme_btc_m15_confluencia.pine](mneme_btc_m15_confluencia.pine). Hipotese experimental: duas ou mais familias tecnicas concordando na vela fechada podem justificar uma entrada simulada. Nao ha vantagem estatistica medida.

## Regra de decisao

Todas as familias habilitadas sao avaliadas juntas. Cada familia da no maximo um voto: compra, venda ou neutro. Variantes da mesma familia nao contam duas vezes. Volume alto sozinho nao tem direcao e nao e um voto. Combinacoes derivadas (por exemplo FVG + varredura) nao recebem voto adicional aos componentes.

- Compra: ao menos o minimo configurado de familias em compra, com menos de duas em venda.
- Venda short: ao menos o minimo configurado em venda, com menos de duas em compra, e short habilitado.
- Duas compras e duas vendas, ou mais: conflito, sem entrada, mesmo que um lado tenha maioria. Aumentar o minimo de entrada nao aumenta o limite de tolerancia a votos contrarios.
- Um voto em cada lado ou apenas um voto: sem entrada. Nao acumula sinais de velas diferentes para criar confluencia; os estados que possuem validade propria (divergencia, reteste) continuam ativos pela janela configurada.
- Uma posicao por vez, sem piramidar e sem inverter por sinal oposto. As saidas continuam por stop, alvo ou tempo.

O painel mostra os 27 votos da ultima vela processada. A linha **Acao operacional** separa o sinal da permissao de enviar ordem, indicando pausa, limite diario, short desabilitado, posicao existente ou ausencia de sinal. A etiqueta e o comentario de cada entrada registram quais familias participaram. A configuracao **Mostrar painel** pode ocultar a lista; **Desenhar medias, bandas, niveis e VWAP** controla as linhas.

## Familias incluidas

| Familia | Regra / origem |
|---|---|
| Tendencia / EMA | Medias 9/21/50 alinhadas com ADX/estrutura, ou cruzamento 9/21; inclui cruzamento filtrado por VWAP, sem voto adicional |
| MACD | Cruzamento do histograma por zero |
| RSI / RSI curto | Extremo e retorno do RSI14, ou retorno do RSI4 de 80/20; conflitos entre variantes neutralizam |
| Bollinger | Fechamento fora da banda ou retorno a banda; inclui variante de retorno filtrada por RSI |
| Rompimento / Donchian | Rompimento de pivo anterior ou canal anterior, no maximo um voto |
| Engolfo | Corpo engloba o corpo contrario anterior |
| Martelo / estrela | Proporcoes de sombra/corpo e sombra/amplitude |
| Varredura / Wyckoff spring | Varrida e retorno ao nivel; spring e uma variante com consolidacao recente |
| FVG | Desequilibrio de tres velas ativo, dentro da distancia ATR |
| Fibonacci | Zona de retracao da ultima perna confirmada |
| Suporte / resistencia | Distancia ao ultimo pivo confirmado ou rejeicao por engolfo/pin bar; inclui filtro de inclinacao EMA10, sem voto adicional |
| Estrutura | Dois ultimos topos e fundos crescentes ou decrescentes |
| Order block | Ultima vela contraria antes de rompimento de estrutura, ate invalidacao |
| Divergencia RSI | Preco e RSI divergentes nos pivos confirmados; validade configuravel |
| VWAP | Fechamento acima/abaixo do VWAP do dia da bolsa |
| Reteste | Retorno ao nivel guardado no rompimento recente |
| LTA / LTB | Toque na reta dos dois ultimos fundos/topos confirmados |
| Triangulo | Retas convergentes com cruzamento da distancia projetada |
| Perfil de volume / POC | Reversao ao POC e variante de toque, agrupadas; conflito neutraliza |
| Ichimoku | Fora da nuvem deslocada do passado, com Tenkan/Kijun alinhados |
| Falso rompimento | Retorno contrario ao rompimento recente |
| Topo / fundo duplos | Proximidade entre extremos confirmados e lado do nivel |
| OCO / OCO invertido | Tres extremos, ombros proximos e ruptura do pescoco |
| VSA | Volume alto com amplitude estreita, contrario ao movimento recente |
| Canal Fimathe experimental | Canal congelado de N velas e rompimento de uma amplitude adicional |
| Tres velas da mesma cor | Continuacao apos tres corpos de mesma direcao em M15 |
| Reversao forte de 1h | Retorno de quatro barras M15 contra desvio amostral em 96 barras M15 |

As formalizacoes principais estao em `mneme/leitura.py`, `mneme/metodologias.py`, `mneme/laboratorio/combinacoes.py`, `mneme/laboratorio/tecnicas.py` e no catalogo `mneme/setups/__init__.py`. Isto e uma **adaptacao experimental para Pine**, nao uma exportacao dos modelos ou prova de equivalencia numerica. RSI, ATR e ADX do Pine usam inicializacao distinta do Python; Bollinger usa desvio populacional, enquanto o setup Bollinger+RSI usa amostral no Python. Divergencias simultaneamente recentes sao neutralizadas aqui (o Python prioriza a baixista). Pivo e sinal nunca sao desenhados retroativamente como se fossem conhecidos antes da confirmacao.

Os setups do catalogo recebem M1 originalmente: aqui os periodos de indicadores sao aplicados em **M15**, uma nova hipotese. Tres velas significam 45 minutos, nao tres minutos; RSI4 significa quatro candles M15. Para o movimento forte de uma hora, 60 candles M1 foram convertidos para quatro M15 e a janela de 24 horas para 96 M15. Isso preserva as duracoes, mas amostra retornos a cada 15 minutos e produz desvio diferente do M1. Nao transfira acerto ou rentabilidade medidos no M1 para este experimento.

FVG guarda ambas as bordas originais: um fechamento dentro da zona nao a invalida; um fechamento alem da borda distante invalida. Isso corrige no Pine a referencia movel de invalidacao herdada da formalizacao Python, que nao foi alterada nesta tarefa.

A tolerancia de toque LTA/LTB compartilha o parametro de proximidade com suporte/resistencia (exemplo 0,5 ATR); o laboratorio usa 0,25 ATR em LTA/LTB. Ajustar isso conta como outro experimento. Perfil usa volume no preco tipico de cada candle e faixas moveis, como o histograma OHLCV do laboratorio; nao e volume efetivamente negociado em cada preco. O agrupamento de perfil e toque POC neutraliza sinais contrarios perto do POC.

Fimathe usa pavios, forma o primeiro canal a partir do inicio configurado e remarca com as ultimas N velas terminando na saida do **portfolio de confluencia**, permitindo voto na vela seguinte. Um canal de amplitude zero nao vota. Usa as saidas comuns ATR/tempo, portanto nao reproduz a carteira ou o gerenciamento proprio da estrategia Python. A versao discricionaria da metodologia nao foi reproduzida.

## Limites do escopo

As 27 familias cobrem as regras tecnicas portadas, incluindo o catalogo de setups e agrupando variantes. **Nao significam todo o conhecimento do MNEME:** seguir traders, modelos ML/DL, noticias/RAG, on-chain, livro de ofertas e fluxo real de negocios continuam no Python ou dependem de fontes externas. Elliott e harmonicos nao possuem regra operacional formalizada nesse laboratorio. O script nao inventa votos para esses dados e nao acessa o servidor MNEME.

Familias diferentes ainda podem ser correlacionadas (por exemplo estrutura e suporte). Duas confirmacoes nao sao duas evidencias estatisticamente independentes nem probabilidade de lucro. A estrategia de confluencia inteira precisa de validacao propria, em periodo futuro sem ajuste, custos estressados, amostra adequada e correcao pela quantidade de hipoteses tentadas.

## Mercado, execucao e risco

Use velas convencionais de **15 minutos** em **BINANCE:BTCUSDT** (spot) ou **BINANCE:BTCUSDT.P** (perpetuo). Short em ticker spot e **sintetico no emulador**, nao permissao de operar vendido na corretora. Para avaliar short em derivativos, use o contrato correto e considere funding, que nao e modelado aqui.

O script inicia pausado. Para ativar, revise os inputs e as Propriedades: exemplos de capital USD 10.000, 10% do patrimonio por entrada, comissao 0,1% por preenchimento, slippage 10 ticks e margem 100%. Os parametros sao editaveis e nao otimizados. Confirmacoes precisam ocorrer em vela fechada; preenchimento de mercado na abertura seguinte; sem recalculo a cada tick ou apos preenchimentos. Bracket enviado junto da entrada, relativo ao preco preenchido e congelado pelo ATR do sinal. O emulador pode inferir a ordem de stop e alvo dentro da mesma vela: confira com dados menores/Bar Magnifier quando disponivel.

Meta diaria e limite de perda possuem inputs proprios deste experimento, exemplos 3% e 2%. O dia vira em Brasilia. A base e o patrimonio do fechamento anterior a primeira vela do dia, incluindo resultado em aberto; se uma posicao carregada perder na primeira vela, essa perda conta. Atingir qualquer limite trava novas entradas ate o dia seguinte, mantendo saidas. Esses inputs **nao leem Configuracoes do site**, nem substituem o kill switch ou os limites do motor Python. Stops, gaps e atualizacao somente por fechamento podem ultrapassar o limite diario configurado.

O inicio minimo e 07/11/2026 UTC para preservar o historico selado. Uma entrada marcada antes do horario atual pode ter sido recalculada sobre candles ja fechados depois desse inicio; nao prova que uma ordem foi observada ao vivo. Nenhum resultado anterior autoriza dinheiro real.

## Teste da decisao

[teste_confluencia.pine](teste_confluencia.pine) tem 11 cenarios de decisao e seis verificacoes de FVG com resultados literais, incluindo zero/um voto, compra, venda, conflito, veto contrario ao aumentar o minimo e fechamento dentro/fora do gap original. Para executar, copie do arquivo de producao os blocos `decidir` (BEGIN/END DECISAO) e `manterGap` (BEGIN/END FVG) para os locais indicados no teste e compile no TradingView. Ele chama as funcoes reais; nao implementa outro simulador. Falha gera `runtime.error`; sucesso exibe o painel verde. Nao adicione o teste ao layout operacional ao mesmo tempo que a estrategia.

Teste de decisao e compilacao nao provam equivalencia de todas as 27 familias, preenchimento intrabar nem rentabilidade. O motor Python e os servicos de nuvem nao foram alterados.

## Verificacao inicial em 07/11/2026 (versao anterior, 25 familias)

- Etapa RED: o teste inicial acusou funcao `decidir` ausente. Depois, dois cenarios adicionais acusaram falha em tempo de execucao contra a versao que permitia votos contrarios ao aumentar o minimo.
- Etapa GREEN: os 11 cenarios passaram no Pine, com painel de sucesso observado no grafico, usando a funcao extraida da producao. Uma revisao adversarial isolada encontrou problemas no limite diario, no veto configuravel e na representacao do toque POC; foram corrigidos e a segunda revisao nao encontrou problema concreto restante. Nao foi realizada revisao por outro modelo externo.
- A versao de 25 familias compilou, sem erro de execucao observado. O texto copiado de volta do editor coincidiu integralmente com o arquivo inserido. Propriedades e 25 familias habilitadas foram conferidas na interface. Simulacao, short e minimo 2 ficaram ativos em BINANCE:BTCUSDT M15. O layout informou **All changes saved**.
- O relatorio recalculado mostrou uma compra e sua saida por tempo maximo. Na ultima vela processada, o painel mostrou 6 compras / 2 vendas e **CONFLITO: SEM ENTRADA**, exercitando o veto no grafico. Uma operacao nao valida desempenho; os preenchimentos especificos de stop/alvo e todas as familias individuais nao foram testados exaustivamente.
- O script de teste foi substituido pela estrategia operacional no grafico. A biblioteca de scripts existentes nao foi sobrescrita; o arquivo local de producao continua sendo a copia recuperavel. Nao foi feita publicacao publica no TradingView nem commit/push no Git.
- A suite Python nao esta disponivel nesta maquina (`python -m pytest`: `No module named pytest`); nao houve execucao na A1. A varredura `scripts/sigilo.sh` esta ausente nesta copia, e nenhum commit foi criado. O diff passou na verificacao de espacos do Git.

## Segunda revisao, por outro modelo

Revisao estatica independente por GPT-6 Astra, solicitada pelo usuario em 07/11/2026. Identificou cobertura incompleta do catalogo e das variantes, invalidacao movel do FVG, remarcacao Fimathe distinta, painel que confundia direcao com permissao operacional e bolsa sem restricao. Correcoes: 27 familias com inventario do catalogo, bordas FVG originais, canal remarcado na saida com janela terminando nela, linha de acao operacional e filtro Binance. A rechecagem tambem identificou aquecimento prematuro do canal e canal degenerado: agora a remarcacao exige N velas elegiveis desde inicio, preserva a acumulacao anterior e reavalia canal de amplitude zero. O FVG Python nao foi alterado.

Os testes de FVG passaram a verificar `na` explicitamente nos retornos que devem existir, pois uma comparacao numerica isolada poderia aceitar valor ausente. O relatorio anterior de 25 familias permanece acima como evidencia historica, sem atribui-lo automaticamente a esta revisao. A revisao estatica nao mede rentabilidade nem substitui verificacao de preenchimentos intrabar.

Rechecagem final do segundo modelo: os achados foram resolvidos no codigo relido, inclusive os tres casos adicionais de Fimathe e teste de FVG. No TradingView, um mutante que retornava sempre `na` falhou com `FVG de alta invalidado dentro da zona original`; com as funcoes reais, o painel mostrou **PASSOU: confluencia (11) + FVG (6)**. A estrategia de 27 familias compilou e o texto copiado do editor coincidiu integralmente com o arquivo local. Todas as 27 familias foram conferidas habilitadas, com minimo 2, shorts simulados e mesmos custos/risco. A simulacao foi reativada e o layout confirmou **All changes saved**. O painel final identificou BINANCE:BTCUSDT M15, 6 compras / 3 vendas, conflito e acao operacional **GERINDO POSICAO**. Isso valida o estado observado; nao constitui teste exaustivo das 27 familias, dos preenchimentos ou da virada diaria.
