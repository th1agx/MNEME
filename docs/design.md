# MNEME: design

Skills instaladas em `.claude/skills/`: **frontend-design** (Anthropic) para o processo e **power** (typeui) como referência de tokens. A primeira versão seguiu o Power ao pé da letra (Oswald gigante e mono em tudo) e foi descartada por parecer feita por IA.

## Conceito

Tela de corretora para copy trading: densa, discreta e familiar para quem já usa exchange. Nada de letreiro gigante: o destaque é o **último sinal em formato de boleta** (lado, ativo, valor sugerido, trader, atraso, motivo).

## Tokens

| Token | Valor | Uso |
|---|---|---|
| `bg` | `#0b0e11` | fundo da página |
| `panel` | `#161a1e` | painéis |
| `raise` | `#1e2329` | hover, botões, etiquetas |
| `line` | `#2b3139` | divisórias |
| `text` | `#eaecef` | texto principal |
| `muted` | `#848e9c` | texto secundário |
| `up` | `#0ecb81` | compra, PnL positivo |
| `down` | `#f6465d` | venda, PnL negativo |
| `warn` | `#f0b90b` | atraso, pausa |

Fonte única: **IBM Plex Sans** com números tabulares, 12px de base, títulos de painel em 14px peso 500. Sem fonte mono e sem caixa alta.

Raio de 4px, painéis separados por 4px de respiro.

## Hierarquia e telas menores

- A barra principal reúne navegação, modo e controles; a conexão aparece em uma faixa própria para não disputar espaço com os botões.
- O resumo da carteira antecede a boleta: saldo livre, resultado do dia, capital em posições e traders acompanhados. Os valores vêm do mesmo estado usado no restante do painel, com o contexto de execução explícito.
- Os atalhos Sinais, Carteira e Histórico levam às seções da própria página.
- Em telas médias, o painel vira uma coluna com dois painéis por linha na área complementar. No celular, os painéis ficam em uma coluna e o resumo em duas. Tabelas largas rolam dentro do painel.
- A navegação por teclado inclui um atalho para o conteúdo. A preferência por movimento reduzido desliga animações e transições.
- A classe `app-bar` pertence ao cabeçalho; as barras dos fatores de score usam `.factor .bar` e não herdam o layout do cabeçalho.

## Regras

- Cor só para lado da operação e risco.
- Sem animação decorativa: só o ticker e o realce de linha/boleta quando chega sinal novo.
- Textos curtos, em português direto, com o vocabulário de corretora: sinal, boleta, fluxo, carteira, limites.
- "Simulado" e o atraso aparecem sempre que forem relevantes.
