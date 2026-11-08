---
name: mneme-portao-e9
description: Use ao construir ou mudar o ciclo de aprendizado do MNEME (E9) - hipóteses automáticas, fábrica de experimentos, retreino, registro de modelos, campeão e desafiante, promoção, rollback - ou qualquer laço em que um agente melhora o próprio sistema. Define o que o agente pode mudar sozinho e o que é travado ou humano.
---

# Portão do E9: o que o agente pode mudar sozinho

O E9 está descrito no Vault (`09-system-knowledge/Proposta - inteligência híbrida multiagente`). Esta skill define as fronteiras do laço de melhoria. Ela não muda o Charter nem o roadmap.

## Regra

O agente **propõe**; o arcabouço define o que pode ser mudado, como é medido e quem aprova. Se o agente puder mudar a régua, ele vai otimizar a régua e não o mercado.

## As quatro superfícies do MNEME

| Superfície | O que entra | Regra |
|---|---|---|
| **Travada** | Validação do laboratório (purga, embargo, placebo, atraso, custos), critérios de promoção, correção para múltiplos testes, área selada, alvo de cada estatística | O agente lê e pode sugerir mudança, mas nunca avalia um candidato com uma régua que ele mesmo alterou. Mudança na régua é humana e vale só para as rodadas seguintes |
| **Editável** | Especificação de experimento, desafiante (modelo, atributos, parâmetros), rascunho de hipótese, texto de nota | O laço pode criar e alterar à vontade |
| **Só de acréscimo** | `experimentos.jsonl`, fila de hipóteses, diário, quadro de evidências, notas de resultado negativo | Pode acrescentar; nunca reescrever nem apagar. Tentativa ruim fica registrada para não ser testada de novo |
| **Humana** | Promoção a campeão, `operacao.json` e a tela de Configurações, limites de risco, dinheiro real, Charter, roadmap, credenciais | Só com aprovação explícita do dono |

## O laço

```
ler o estado travado → escolher hipótese (registrada antes de ver o resultado)
→ mudar só a superfície editável → rodar a validação travada
→ registrar tudo (inclusive o que falhou) → se passou: desafiante em sombra
→ comparação pareada com o campeão → portão → aprovação humana → promoção
→ monitorar → rollback para a última versão aprovada se deteriorar
```

Propriedades obrigatórias:
- A validação fica fora da superfície editável.
- Toda versão tem identidade (impressão dos dados, commit, parâmetros) e o ponteiro do campeão é a única coisa que o motor lê. Rollback é trocar o ponteiro.
- Orçamento fixo por rodada (CPU, tempo, número de testes), com um trabalho pesado por vez na A1, 1 thread, CPUQuota e nice 19.
- Política escrita para travamento, tempo esgotado e resultado inconclusivo.

## Contra o agente burlar a métrica

Suponha que o laço vai aprender o arcabouço. Bloqueie:
- avaliar com critérios alterados na mesma rodada;
- abrir a área selada mais de uma vez por candidato, ou escolher o candidato depois de olhar a área selada;
- relatar só a média e esconder a dimensão que piorou (mercado, regime, horizonte, modalidade);
- citar fonte que não foi lida, ou resultado que não está no registro;
- deixar de registrar tentativas que falharam.

## Busca disciplinada

1. Antes de gastar orçamento grande, confira se a ideia já foi testada (registro, Vault, notas negativas).
2. Preserve as rejeitadas, com o motivo.
3. Quando várias melhorias se somam, faça poda: tire uma de cada vez e veja se o resultado se mantém.
4. Com qualidade igual, prefira o mais simples.
5. Verificação separada antes da promoção: a sombra ao vivo não é a mesma amostra do teste.

## Monitoramento

O monitor só lê e relata: campeão atual, desafiantes em sombra, alarmes, laços parados, divergência entre o registro e o que se afirma, próximo passo e bloqueio. Ele cita o arquivo ou a tabela de onde tirou cada afirmação.

## Como relatar

Para cada rodada: hipótese registrada (com data), superfícies tocadas, régua usada (versão), resultado por dimensão, número total de testes até aqui, decisão (rejeitada, sombra, aguardando aprovação) e como desfazer.
