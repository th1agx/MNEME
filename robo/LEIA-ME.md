# Robô MNEME (Python)

O robô que aprende com o mercado e opera Forex, ouro, cripto e expiração fixa, **no simulado** antes de qualquer dinheiro real. A definição do produto está em [docs/PRODUCT_CHARTER.md](../docs/PRODUCT_CHARTER.md).

## Seguir traders (`python -m mneme`)

Esta é uma das estratégias. O motor multi-mercado está em `mneme/motor/`. A cada minuto:

1. Lê as operações recentes dos traders no provedor de sinais.
2. Mede a taxa de acerto de **todo** trader pelas operações que ele encerra (30 dias), esteja ou não no ranking.
3. **Estratégia "seguir traders"** em Solana: compra quando a maioria dos traders de alto acerto compra o mesmo token e vende quando a maioria dos que formaram a entrada vende.
4. Respeita a meta e o limite do dia (meia-noite de Brasília).
5. Grava tudo no banco local `robo/dados/mneme.db` (carteira simulada de US$ 200.000, com 0,1% de taxa e 0,5% de slippage em cada ponta).

Os parâmetros vêm da tela de **Configurações** do site (`/api/training/settings`). Sem eles, o robô só observa.

## Onde roda

O robô roda na **Oracle A1**, em Docker Compose ([compose.yaml](compose.yaml)): o serviço `traders` (seguir traders e teste ao vivo) e os demais serviços, todos com `restart: always`, health check por batimento e logs com rodízio. O Docker sobe sozinho quando a máquina reinicia. O `.env` da A1 (`~/mneme/.env`) guarda só as chaves do provedor de sinais e do Telegram. Uma trava impede duas cópias do robô de traders no mesmo banco.

```bash
ssh mneme-a1 'cd ~/mneme/robo && docker compose ps && docker compose logs --tail 20 traders'
```

## Desenvolvimento

O computador de cada colaborador serve para desenvolver, administrar e ver o Vault no Obsidian. A configuração inteira é um comando: [colaborar/LEIA-ME.md](../colaborar/LEIA-ME.md). Na pasta `robo/`:

```bash
uv sync
uv run pytest -q
```

No macOS, o LightGBM usa a libomp que vem com o scikit-learn (`mneme/openmp.py`), sem Homebrew. O `rodar.sh` roda o robô só para teste, num banco separado (`dados/desenvolvimento.db`).

## Organização

| Arquivo | Para quê |
|---|---|
| `mneme/sinais.py` | Cliente do provedor de sinais |
| `mneme/conectores/solana.py` | Preço e liquidez de tokens de Solana |
| `mneme/acerto.py` | Mede o acerto de cada trader |
| `mneme/estrategias/seguir_traders.py` | Regra de entrada e saída |
| `mneme/carteira.py` | Carteira simulada, meta e limite do dia |
| `mneme/carteira_tecnicas.py` | Carteira simulada ao vivo por técnica e confluência, sem enviar ordens |
| `mneme/motor/` | O robô multi-mercado: decisão, risco, sinal, execução simulada, diário e contexto da LLM |
| `mneme/aprendizado.py` | Ciclo de aprendizado (E9): hipótese, teste no laboratório, veredito e nota no Vault; de hora em hora na A1 ([aprendizado.crontab](aprendizado.crontab)) |
| `mneme/vault.py` | Knowledge Vault: notas em Markdown e Git, indexadas no RAG. Ver `docs/VAULT.md` |
| `mneme/e9/` | E9 v2: régua estatística travada (`regua.py`, versão com impressão fixada em teste), dossiê das decisões como de cada momento (`dossie.py`) , atribuição por dimensão com regime (`atribuicao.py`), hipóteses tipadas com a contrária num registro só de acréscimo (`hipoteses.py`, em `dados/e9/hipoteses.jsonl`) e o propositor que une dossiê e LLM (`propositor.py`). Notas no Vault: "E9 - onde o motor acerta e erra" e "E9 - hipóteses registradas". Plano no Vault: `09-system-knowledge/Plano E9 v2 - aprendizado contínuo` |
| `mneme/quadro/` | Quadro de evidências (F1, em sombra): especialistas gravam evidências tipadas e restrições de risco por oportunidade, sem influir no motor. Serviço `quadro`, só leitura em `dados/` e escrita em `dados/quadro/`. `python -m mneme.quadro resumo` e `reproduzir --amostra 20`. Plano no Vault: `09-system-knowledge/Plano F1 - quadro de evidências` |
| `pine/mneme_confluencia.pine` | Confluência no gráfico do TradingView, gerada por `mneme.motor.pine` |
| `mneme/ciclo.py` | Um ciclo completo do robô |
| `mneme/banco.py` | Esquema do banco (SQLite agora, Postgres no servidor) |

## Base de conhecimento e setups

`conhecimento/` guarda o que foi pesquisado na web (conceitos, setups e estudos, com as fontes). Esses são os documentos do RAG. Cada setup vira uma regra em `mneme/setups/` e é medido pelo laboratório, descrito abaixo.

O resultado de cada setup fica em `conhecimento/setups.md`. Na medição de 05/11/2026, com correção por múltiplos testes, nenhum setup passou do empate de 54,05%; os de reversão têm vantagem real sobre 50%.

### Teste ao vivo

Desde 31/10/2026, a cada ciclo o robô procura o sinal de Bollinger + RSI nas velas recém-fechadas de BTC, ETH e SOL, grava em `sinais_ao_vivo` e confere o resultado 15 minutos depois (`mneme/ao_vivo.py`). Nada vai para o Telegram. Placar:

```bash
uv run python -m mneme.ao_vivo
```

O setup só vira dica depois de algumas semanas acima do empate.

## Dados de mercado e leitura

`mneme/dados/` coleta velas de 1 minuto da Binance em Parquet, um arquivo por par e por dia, em `dados/mercado/`. O histórico vem dos arquivos públicos; o ao vivo vem do WebSocket; qualquer queda é recuperada por REST. Cada vela guarda a hora em que chegou, para `ArmazemVelas.ler(como_de=...)` devolver só o que já se sabia naquele instante. Vela incoerente vai para `dados/mercado/quarentena/`.

`mneme/indicadores.py` calcula médias, RSI, MACD, Bollinger, ATR, ADX, OBV, VWAP e delta de volume, conferidos com o TA-Lib nos testes. `mneme/leitura.py` monta, vela a vela, os atributos para modelos e backtest: tendência, estrutura de topos e fundos, suporte e resistência, rompimentos, consolidação e padrões. Nada olha o futuro, e um teste garante isso.

```bash
uv run python -m mneme.dados importar --meses 24
uv run python -m mneme.dados resumo
uv run python -m mneme.dados ler BTCUSDT --tempo 15min
uv run python -m mneme.dados coletar
```

Na Oracle A1, a coleta roda em Docker Compose, com limite de memória e reinício automático. Não usa chaves:

```bash
docker compose up -d --build
```

### Fluxo e derivativos

`mneme/dados/coleta_fluxo.py` coleta trades, livro de ofertas (20 níveis, uma foto por segundo), funding, open interest e liquidações em `dados/mercado/fluxo/`, em um serviço separado das velas. Numa queda, os trades são recuperados por REST; o livro não tem recuperação, e a lacuna fica visível. Dias fechados são compactados; o livro fica 30 dias e os trades, 365. Com o disco em 85%, o livro para de ser gravado; em 92%, os trades também. `mneme/fluxo.py` agrega tudo por minuto para modelos e backtest.

```bash
uv run python -m mneme.dados fluxo
uv run python -m mneme.dados importar-derivativos --meses 24
uv run python -m mneme.dados resumo-fluxo
```

## Laboratório

`mneme/laboratorio/` mede estratégias sem vazamento: entrada depois do sinal, custos por modalidade, walk-forward com purga e embargo, correção por múltiplos testes (Holm, Sharpe deflacionado, PBO), placebos e um detector de sinal que olha o futuro. Toda tentativa fica em `dados/laboratorio/experimentos.jsonl`.

```bash
uv run python -m mneme.laboratorio setups --minutos 5 15 --payout 0.85
uv run python -m mneme.laboratorio spot --alvo 15 --stop 15 --velas 480
uv run python -m mneme.laboratorio modelos --horizontes 5 15
```

## Próximos passos

A ordem de implementação está em `docs/architecture/ROADMAP.md`.

### Fimathe no conjunto de estratégias

A Fimathe experimental participa do mesmo catálogo de setups e do registro de experimentos acima. Os parâmetros são definidos em Configurações → Fimathe e exportados em JSON. Sem regra completa, não gera entradas; um contrato configurado para XAUUSD não é usado nos pares da Binance.

```bash
uv run python -m mneme.laboratorio catalogo
uv run python -m mneme.laboratorio --config-estrategias dados/fimathe-config.json --pares XAUUSD setups --minutos 5 15
uv run python -m mneme.laboratorio --config-estrategias dados/fimathe-config.json --pares XAUUSD spot
uv run python -m mneme.laboratorio fimathe --config dados/fimathe-config.json --csv dados/xauusd.csv --fonte "Exportação XAUUSD da corretora"
```

O teste de posições mantém o stop/alvo, lote e custos da Fimathe, sem substituir sua regra pelas barreiras de ATR dos outros setups. A interface comum está em Treino Bot → Estratégias em avaliação, com importação dos resultados de `dados/laboratorio/`. Não há aba explicativa separada. Continua somente simulada, sem promoção automática para execução ao vivo.
