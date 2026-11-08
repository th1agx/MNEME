---
name: mneme-poder-estatistico
description: Use para decidir quantas operações, sinais, dias ou pontos são necessários para provar um resultado no MNEME - "58% de acerto já é real?", "quantos dias de sombra?", "quantos pontos para comparar modelos?" - e para o efeito mínimo detectável com a amostra que temos.
---

# Poder estatístico e tamanho de amostra no MNEME

Use junto com `mneme-auditoria-backtest` e `mneme-hipoteses`. O ambiente já tem scipy e numpy: não instale nada para isso.

## Regra

Antes de testar, decida o **efeito mínimo que importa** e calcule a amostra. Não invente o efeito, não use o efeito que acabou de medir (poder calculado depois é circular) e entregue uma faixa, não um número só.

## O efeito que importa

No MNEME ele vem da economia da operação, não de convenção:
- **Expiração fixa:** empate = 1 / (1 + payout). Com payout de 85%, empate de 54,05%. O efeito mínimo é a folga sobre o empate que paga o risco (por exemplo, acerto de 56% contra 54,05%).
- **Com stop e alvo:** expectativa líquida por operação acima de zero depois de taxa, spread, slippage e atraso.
- **Comparação de modelos:** diferença de AUC ou de IC que mudaria a decisão de promover.
- **Calibração:** erro máximo tolerável por faixa de probabilidade.

## Contas rápidas (scipy)

Acerto contra o empate (proporção, teste de um lado se a pergunta é "passa do empate"):

```python
from scipy.stats import norm
def n_para_acerto(p_real, p_empate, alfa=0.05, poder=0.8):
    za, zb = norm.ppf(1 - alfa), norm.ppf(poder)
    num = za * (p_empate * (1 - p_empate)) ** 0.5 + zb * (p_real * (1 - p_real)) ** 0.5
    return (num / (p_real - p_empate)) ** 2
# n_para_acerto(0.56, 0.5405) ≈ 4.000 operações independentes
# n_para_acerto(0.58, 0.5405) ≈ 1.000
```

Quando o desenho não cabe numa fórmula (modelo, regime, várias estratégias juntas), **simule**: gere dados com o efeito suposto e o ruído real, rode exatamente a análise planejada, repita mais de 1.000 vezes e conte quantas vezes ela detecta o efeito. Relate o intervalo de Monte Carlo.

## Ajustes que mudam tudo no MNEME

- **Operações não são independentes.** Estratégias no mesmo ativo e na mesma vela, sinais de 1 minuto seguidos e posições que se sobrepõem contam quase como uma só. Use a **amostra efetiva**: agrupe por vela ou por dia, ou aplique o efeito de desenho `1 + (m − 1) · correlação` dentro de cada grupo. Exemplo real (diário de 06 a 08/11/2026): 374 operações encerradas aconteceram em só 294 minutos distintos, e minutos seguidos no mesmo ativo também são correlacionados. A amostra efetiva é menor que 374; tratar as 374 como independentes infla a confiança.
- **Múltiplos testes.** O E9 testa muitas hipóteses: calcule a amostra no alfa corrigido (Holm ou controle de descobertas falsas) da família inteira, não de cada teste.
- **Perdas da amostra.** Operações sem preço, empates e dias sem dado reduzem o n analisado: aumente o n planejado.
- **Regimes.** Se o resultado precisa valer por regime ou por mercado, cada parte precisa do seu n; o total não basta.
- **Duas metades.** O critério do laboratório exige as duas metades acima do empate: planeje o n de cada metade.

## Fluxo

1. Escreva a pergunta, a unidade independente (operação, vela, dia) e a análise exata.
2. Defina o efeito mínimo pela economia (acima), com a justificativa.
3. Fixe alfa (corrigido para a família) e poder (0,8 em geral; 0,9 para promoção).
4. Calcule (fórmula ou simulação) e faça a **sensibilidade**: o n para vários efeitos plausíveis.
5. Aplique os ajustes de dependência, múltiplos testes e perdas.
6. Converta em tempo: "a esta taxa de sinais, isso leva X dias".

## Erros comuns

1. Inventar o efeito ou copiar o de um estudo curto e otimista.
2. Relatar um número só, sem faixa.
3. Calcular o poder com o resultado que acabou de sair.
4. Tratar operações correlacionadas como independentes.
5. Esquecer a correção da família de testes do E9.
6. Usar fórmula de proporção para uma análise que é de modelo (aí, simule).

## Como relatar

Pergunta, unidade independente, efeito mínimo e o porquê, alfa corrigido, poder, n calculado com a faixa de sensibilidade, ajustes aplicados e quanto tempo de coleta isso significa.
