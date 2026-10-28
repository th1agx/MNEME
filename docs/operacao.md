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

## Testes

```bash
npm test
npm run typecheck
```
