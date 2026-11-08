---
name: mneme-avaliacao
description: Use ao avaliar especialistas, o Coordenador, papéis da LLM, o quadro de evidências ou qualquer mudança de arquitetura do MNEME - antes de dizer que algo "melhorou". Checagem determinística primeiro, resultado por dimensão e comparação com a referência, sem nota ponderada arbitrária.
---

# Avaliação de componentes do MNEME

O produto é definido em `docs/PRODUCT_CHARTER.md`; esta skill não muda nada dele.

Para backtest, modelo e estratégia, use também `mneme-auditoria-backtest`. Esta skill cobre a avaliação dos componentes da arquitetura (especialistas, Coordenador, papéis da LLM, quadro, filas).

## Regra

Uma mudança só "melhora" o MNEME se vencer a referência medida, fora da amostra, depois de custos, sem piorar nenhuma dimensão crítica. Nota única esconde falha.

## Ordem da avaliação

1. **Checagem determinística primeiro.** Esquema válido, campos obrigatórios, nenhum dado depois do instante da decisão, idempotência, dependências registradas, reprodução idêntica. Se falhar aqui, não há o que medir depois.
2. **Referência antes da mudança.** Grave a linha de base (latência do motor, acerto, calibração, recursos) num período definido, antes de ligar o componente.
3. **Mesmos casos, mesmo orçamento.** Referência e candidato nos mesmos instantes, com o mesmo custo e a mesma régua.
4. **Resultado por dimensão,** nunca só a média: por mercado, ativo, modalidade, horizonte, regime e período.
5. **Julgamento por LLM só no fim,** e só para o que não tem verdade medível (por exemplo, a clareza de uma nota). Decisão operacional nunca depende de juiz LLM.

## Dimensões do MNEME

| Dimensão | Medida | Falha crítica (não compensa com o resto) |
|---|---|---|
| Correção temporal | Nenhuma evidência com `dados_ate` depois do instante | Qualquer caso |
| Cobertura | Fração dos instantes com resposta ou falha registrada | Lacuna silenciosa |
| Valor preditivo | AUC, IC de retorno, R² de volatilidade, com intervalo, por fonte e combinado | Pior que a referência simples |
| Calibração | Brier, erro de calibração por faixa | Probabilidade marcada como calibrada sem validação |
| Contribuição incremental | Ganho da fonte sobre o resto (ablação) | Fonte que não acrescenta continua pesando |
| Custo operacional | Latência do motor (mediana e p99), CPU, RAM, disco, tarefas da LLM | Motor fora do orçamento |
| Segurança | Restrição do Risk nunca sobrescrita; texto externo nunca vira ação | Qualquer caso |
| Reprodutibilidade | Recalcular dá o mesmo resultado | Diferença sem explicação |

Não use pesos nem cortes inventados (como "0,7 passa"). Os critérios de passagem são estatísticos e escritos antes do teste: intervalo de confiança, correção para múltiplos testes, efeito mínimo que importa (ver `mneme-poder-estatistico`).

## Conjuntos de casos

- Estratifique por dificuldade e por condição de mercado (calmo, volátil, evento do calendário, dado faltando, fonte fora do ar).
- Inclua casos que devem falhar de propósito: especialista lento, dado atrasado, nota maliciosa, LLM fora do ar. O componente tem que falhar do jeito certo.
- Congele o conjunto de casos de cada avaliação (versão e data).

## Avaliação contínua

- Depois de ligado, compare a cada dia com a linha de base, nos mesmos horários.
- Teste de liga e desliga: desligar o componente por um período conhecido mostra o efeito real sobre o motor.
- Alarme quando uma dimensão crítica piora, com o registro de onde veio a medida.

## Como relatar

Linha de base (período e números), candidato (versão), casos (versão), resultado por dimensão com intervalo, falhas críticas, custo e o que ainda não foi medido.

## Crédito

Adaptada de `evaluation` (commit 8fc51c7) de Context Engineering Agent Skills Contributors ([muratcankoylan/Agent-Skills-for-Context-Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering), MIT, © 2025). Reescrita para o MNEME, sem rubricas com peso nem o script. Origem detalhada e avisos de licença em `docs/skills/origens/mneme-avaliacao.md`.
