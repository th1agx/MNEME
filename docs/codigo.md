# MNEME: arquitetura do código

Camadas no estilo portas e adaptadores (hexagonal). Na web, isso se lê como MVC: o **modelo** é domínio + aplicação, os **controllers** ficam em `interface/http` e as **views** em `public/`.

```
src/
  domain/            Regras puras, sem IO. Testáveis isoladamente.
    events.ts          TraderEvent, TopTrader, chaves estáveis
    settings.ts        Schema (zod) e padrões das configurações
    scoring.ts         Score de confiança 0–100 com fatores explicados
    policies.ts        Entrada, tamanho, limites de risco, saída
    consensus.ts       Detecção de consenso entre traders
    calibration.ts     Taxa de acerto real por faixa de score
    trading.ts         Signal, Order, Position, cálculo de resultado
  application/       Casos de uso. Dependem só das portas.
    ports.ts           Interfaces: MarketData, OrderExecutor, repositórios…
    signalService.ts   Evento → deduplica → pontua → decide → executa
    tradingService.ts  Abre/fecha posições, limites, idempotência
    positionMonitor.ts Preço a mercado e regras de saída
    leaderboardService.ts, settingsService.ts, dashboardQuery.ts…
  infrastructure/    Adaptadores concretos das portas.
    fomo/              fomoapi.io (REST + WebSocket)
    market/            DexScreener (preço, liquidez, variação)
    execution/         PaperExecutor e JupiterExecutor (Solana)
    persistence/       Repositórios em arquivo (JSON/JSONL)
    demo/              Feed, ranking e mercado fictícios
  interface/http/    Router, controllers e servidor local.
  config/env.ts      Variáveis de ambiente (segredos e infraestrutura).
  main.ts            Raiz de composição: liga implementações às portas.
public/              Views: index.html (painel), settings.html, assets/.
```

## Como os princípios SOLID aparecem

- **Responsabilidade única:** cada serviço faz uma coisa (sinais, execução, monitor de preço, ranking). Regras ficam no domínio; controllers só traduzem HTTP.
- **Aberto/fechado:** novo fornecedor de dados ou nova rede = novo adaptador que implementa a porta, sem mexer nos serviços.
- **Substituição de Liskov:** `PaperExecutor` e `JupiterExecutor` são intercambiáveis pela porta `OrderExecutor`; os testes usam o simulado.
- **Segregação de interfaces:** portas pequenas (`MarketData`, `OrderExecutor`, um repositório por entidade).
- **Inversão de dependência:** serviços recebem portas no construtor; só `main.ts` conhece classes concretas.

## Fluxo de um sinal

1. `AlertsStream` recebe o alerta e `normalizeAlert` converte para `TraderEvent`.
2. `SignalService` (fila, um evento por vez): deduplica pelo `eventId`, filtra o Top, registra consenso.
3. Compra: busca mercado (DexScreener), calcula o score, aplica `entryBlockers` e depois `applyLimits` via `TradingService.plan`.
4. Se válido e o modo executa: `TradingService.open` envia ao executor do modo (simulado ou Solana) com chave de idempotência `open:<eventId>`.
5. Venda do trader: fecha as posições copiadas dele, se "sair junto" estiver ligado. A pausa não bloqueia saídas.
6. `PositionMonitor` atualiza preços e aplica alvo, stop, stop móvel e tempo máximo.

## Segurança da execução real

- Duas chaves para ligar: `LIVE_TRADING=on` **e** `SOLANA_PRIVATE_KEY`. Sem elas o modo real é recusado no servidor, e ao reiniciar volta para simulado.
- A tela pede confirmação explícita para ativar dinheiro real.
- Antes de assinar, a cotação do Jupiter é comparada ao preço de referência; se estiver pior que o slippage configurado, a ordem é recusada.
- Venda nunca passa do saldo da carteira; 0,02 SOL fica reservado para taxas.
- A chave nunca é registrada em log nem enviada a nenhum serviço além da assinatura local; o Jupiter recebe a transação já assinada.
- Escritas na API exigem o cabeçalho `x-mneme`, e o servidor só escuta em 127.0.0.1.
- Do `@solana/web3.js` só são usadas a chave e a transação; as chamadas RPC usam `fetch` próprio.

## Robustez

- **Saídas:** usam um slippage próprio (padrão 10%), maior que o de compra, para um stop executar mesmo em queda rápida. Venda que falha é retentada com espera crescente (15 s, 30 s, 1 min… até 5 min) e gera aviso na terceira falha. A venda manual ignora a espera.
- **Disjuntor:** ordens que falham em sequência (padrão 3) pausam as entradas e avisam. Saídas continuam.
- **Resposta perdida do Jupiter:** a assinatura da transação é conhecida antes do envio. Se o `/execute` não responder, o MNEME consulta a assinatura na rede por até 60 s e, se confirmou, calcula o resultado pela variação de saldo.
- **Sem preço:** o tempo máximo na posição continua valendo.
- **Venda parcial:** com `followTraderMode = proportional`, vende a mesma fração do trader quando o feed informa valor vendido e restante; sem essa informação, vende tudo.
- **Consenso:** quem vendeu o token deixa de contar.
- **Feed:** reconexão com espera crescente; vigia que refaz a conexão após 10 min sem mensagens; ao reconectar, busca em `/v2/alerts` o que passou (duplicados descartados pelo `eventId`). As 200 primeiras mensagens brutas de cada execução ficam em `data/live/raw-samples.jsonl`.
- **Avisos:** Telegram para sinais, compras, vendas, queda do feed, falhas e pausas.
- **Servidor:** Docker com reinício automático, `/api/health` e senha obrigatória quando o painel escuta fora do 127.0.0.1.

## O que ainda não foi verificado com dados reais

- Formato real do feed e do `/v2/alerts` da fomoapi.io (o `npm run check:fomo` confere).
- Envio de uma transação real pelo Jupiter. Já verificado com dados reais: cotação, decimais do token, preço no DexScreener e a resposta de saldo insuficiente.
- Build da imagem Docker.

## Testes

`npm test` cobre o domínio (score, políticas, consenso, calibração, validação), o fluxo completo com executor simulado e os adaptadores (fomoapi, DexScreener e Jupiter com respostas simuladas, incluindo assinatura real da transação).
