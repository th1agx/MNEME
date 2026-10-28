# MNEME: operação

Bot de copy trading do Top de um ranking. Recebe as operações dos traders pelo provedor de sinais, analisa cada compra com um score de risco e, conforme o modo escolhido, só sugere, opera numa carteira simulada ou compra e vende de verdade em Solana pelo [Jupiter](https://jup.ag).

- System design: [system-design.md](system-design.md)
- Código e segurança: [codigo.md](codigo.md)
- Design: [design.md](design.md)
- Servidor 24 h, Telegram e backup: [deploy.md](deploy.md)

## Rodar

Requer Node 22.9+. No Windows PowerShell use `npm.cmd` no lugar de `npm`.

```bash
npm install
npm run demo        # dados fictícios, sem chave
npm start           # dados reais (precisa de SIGNALS_API_KEY, SIGNALS_REST_URL e SIGNALS_WS_URL no .env)
```

Painel em http://localhost:4740 e configurações em http://localhost:4740/configuracoes.

### Gráfico de mercado e ordens

O painel abre em SOL/USDT com 180 velas OHLCV reais da Binance Spot. A moeda e o intervalo (1 minuto a 1 dia) são selecionados no gráfico; há visualização em velas ou linha e atualização a cada 10 segundos enquanto a aba estiver visível. A última vela pode estar em formação. Use o cursor ou as setas do teclado para consultar abertura, máxima, mínima e fechamento.

As cotações usam a API pública de dados de mercado, sem conta ou chave Binance. Elas são reais inclusive quando o MNEME está em demonstração. Se a API falhar, o painel informa a falha e o horário do último histórico recebido; não substitui as velas por dados fictícios.

No Cloudflare Pages, a rota `/api/market/candles` consulta o mercado diretamente e o gráfico funciona mesmo antes de conectar a VPS. Carteira e ordens continuam dependendo do estado do bot; enquanto não há conexão, o painel informa que está aguardando o bot.

Se a rota de mercado retornar erro de servidor ou não puder ser alcançada, o navegador consulta a mesma API pública da Binance diretamente, sem enviar cookies ou credenciais. O histórico continua validado e real. A rota do servidor é tentada novamente após um minuto; recusas de autenticação, validação e limite de uso não acionam essa alternativa. A lista de moedas usa a mesma conexão do gráfico.

Os marcadores C/V identificam o horário das ordens executadas pelo bot e abrem seus detalhes. As faixas de volume distinguem a Binance (USDT) do bot (USD); preço de referência e preço de execução podem divergir. Ordens que falharam aparecem no histórico, sem marcador de execução. O histórico permite filtrar compras, vendas, falhas ou apenas a moeda selecionada e mostra as últimas ordens disponíveis no estado do painel. Em demonstração, as operações do bot são fictícias e aparecem identificadas como simuladas; tokens sem mercado suportado permanecem no histórico.

## Modos

| Modo | O que faz |
|---|---|
| Só sugestões | Mostra o sinal, o score e alerta. Não opera. |
| Simulado | Opera numa carteira de mentira com preços reais, para medir a estratégia. |
| Dinheiro real | Compra e vende sozinho numa carteira Solana dedicada, dentro dos limites. |

Para liberar dinheiro real: crie uma carteira Solana nova só para o bot, coloque pouco saldo e preencha `LIVE_TRADING=on` e `SOLANA_PRIVATE_KEY` no `.env` (veja `.env.example`).

## Como o bot decide

1. **Entrada:** quando alguém do Top compra, o MNEME busca preço e liquidez (DexScreener) e calcula um score de 0 a 100. Entra só se o score passar do mínimo e se todas as regras de entrada forem atendidas.
2. **Score:** soma ponderada de posição no ranking, histórico copiando o trader, consenso do Top, velocidade do sinal, liquidez, se o preço já disparou e convicção do trader. **Não é probabilidade.** A taxa de acerto real por faixa de score aparece no painel e na configuração conforme as posições são encerradas; é ela que diz se "score 90" acerta 90% ou não.
3. **Quanto:** valor fixo, percentual do saldo ou percentual da operação do trader, com mínimo e máximo.
4. **Limites:** posições simultâneas, exposição total, máximo por token e perda máxima no dia.
5. **Saída:** junto com o trader, alvo de lucro, stop, stop móvel ou tempo máximo; o que acontecer primeiro. Também há venda manual no painel.

## Dia da conexão

Tudo abaixo é feito uma vez, na ordem. Nenhum passo envia ordem real até o 6.

1. **Provedor de sinais:** preencha `SIGNALS_API_KEY`, `SIGNALS_REST_URL` e `SIGNALS_WS_URL` no `.env` e rode `npm run check:feed`. Ele lê o ranking e os alertas recentes, escuta o feed por 2 minutos e diz se o formato bate com o MNEME (redes, `userId`, campos) e qual o atraso dos alertas ao vivo. Relatório em `data/live/check-feed.json`.
2. **Rodar em sugestões:** `npm start`, modo *Só sugestões* em Configurações. Conferir sinais chegando com atraso de poucos segundos.
3. **Simulado:** alguns dias no modo *Simulado*, acompanhando o painel "Acerto por score" para escolher o score mínimo.
4. **Carteira:** crie uma carteira Solana nova, coloque pouco SOL, preencha `SOLANA_PRIVATE_KEY` e rode `npm run check:wallet` (lê saldo, preço e pede uma cotação ao Jupiter, sem enviar transação).
5. **Servidor, acesso e avisos:** suba numa VPS com Docker, publique o painel pela Cloudflare (Tunnel + Access) e configure o Telegram, que também aceita comandos como `/status` e `/vender` (docs/deploy.md).
6. **Dinheiro real:** `LIVE_TRADING=on`, valores pequenos (US$ 5 a 10 por ordem), acompanhar as primeiras transações no Solscan.

## Resumos automáticos com IA

Opcionalmente, configure `THESIS_AI=on` e `ANTHROPIC_API_KEY` no `.env` da VPS. Quando o feed trouxer uma tese de um trader acompanhado, o Claude resume o texto, identifica a postura e os riscos citados, atualiza o painel e envia um aviso ao chat definido por `TELEGRAM_CHAT_ID` se o Telegram estiver configurado. A notificação é informativa: não altera score, entrada, tamanho ou saída de posição. Cada tese analisada pode gerar cobrança da Anthropic; configure limites de gasto na conta e monitore o uso antes de deixar ligado continuamente.

Use o bot e o chat privado de operação já existentes. Não envie resumos internos para grupos de assinantes: a entrega paga ainda não tem cadastro, cobrança nem isolamento de comandos. Para o plano de enriquecimento e busca de fontes, veja [inteligência e busca](inteligencia-e-busca.md).

## Testes

```bash
npm test
npm run typecheck
```
