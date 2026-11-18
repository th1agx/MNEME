# MNEME Sinais (extensão do Chrome)

Mostra os sinais do MNEME num card no canto da Quotex ou da IQ Option. **Só desenha:** não lê, não clica e não opera nada na corretora. Quem decide entrar e clica é sempre a pessoa. As regras da Quotex (cláusula 2.5.2 das Rules of Trading Operations) proíbem software operando no lugar do cliente.

## Como chega o sinal

Tudo fica na VPS:
1. O motor decide.
2. O serviço `sinais` lê o diário (só leitura) e responde **apenas dentro da VPS** (127.0.0.1:8787), sem nenhuma porta aberta para a internet.
3. Neste computador, um **túnel SSH** liga o `127.0.0.1:8787` local ao da VPS.
4. A extensão consulta o túnel a cada 2 segundos.

Só aparecem os sinais do cenário escolhido em `dados/digitais/cenario.json` na VPS (exemplo em `robo/digitais_cenario.exemplo.json`). O card identifica a **paridade**, o **timeframe** e a ação sugerida; quando mais de uma paridade estiver configurada, só a que tiver um sinal válido no momento aparece.

## Instalar

1. Configure o acesso à VPS uma vez: `bash colaborar/configurar.sh`.
2. Ligue o túnel: `bash colaborar/tunel-sinais.sh instalar` (no macOS fica ligado sozinho). Confira com `bash colaborar/tunel-sinais.sh testar`.
3. No Chrome, abra `chrome://extensions`, ligue o **Modo do desenvolvedor**, clique em **Carregar sem compactação** e escolha esta pasta (`extensao/`).
4. Nas **opções** da extensão, cole a chave `MNEME_SINAIS_LER` do `.env` (vem no e-mail de chaves do projeto).
5. Abra a corretora: o card aparece no canto inferior direito. Dá para arrastar pelo topo e minimizar.

## O card

- **prepare** (até 1 min antes) → **ENTRE AGORA** (15 s a partir do minuto de entrada) → **em andamento** → **resultado**.
- 🟢 CALL ou 🔴 PUT, ativo, expiração e contagem regressiva. Um som avisa o sinal e a hora de entrar.
- **"entrei" + payout %**: registra na VPS (`dados/digitais/entradas.db`) o que a corretora mostrou. É a captura assistida do Motor 02, que mede o payout e o resultado reais.
