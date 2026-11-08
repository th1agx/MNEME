---
name: mneme-hipoteses
description: Use ao formular, revisar ou registrar hipóteses do MNEME (E9, estudos, papéis Research e Strategy da LLM). Separa observação, hipótese, previsão e evidência, exige rivais e registro antes de ver o resultado.
---

# Hipóteses no MNEME

O produto é definido em `docs/PRODUCT_CHARTER.md`; esta skill não muda nada dele.

Uma hipótese é uma proposta para ser contestada, não um resultado. Ela vira estratégia só depois do laboratório e do portão do E9 (`mneme-portao-aprendizado`).

## Regra

A LLM e os agentes **propõem** hipóteses. Quem rejeita ou aprova é a validação travada do laboratório e, na promoção, uma pessoa. A LLM nunca dá nota, nunca ordena nem aceita hipóteses.

## Não misture os objetos

| Objeto | No MNEME |
|---|---|
| Observação | O que foi medido, com fonte, período e incerteza ("as compras dos traders vêm depois de +34% na hora") |
| Pergunta | O que se quer saber, com escopo (mercado, ativo, modalidade, horizonte) |
| Hipótese | A explicação candidata ("entradas depois de disparada rendem pior") |
| Previsão | O que deve aparecer nos dados se a hipótese valer, escrito antes de olhar |
| Rival | Outra explicação para a mesma observação |
| Controle | Algo que não deveria mudar se a hipótese valer (placebo, outro ativo, outro período) |
| Evidência | O resultado medido; nunca a própria hipótese |

Uma história convincente não é previsão; uma previsão não é evidência; rejeitar uma nula não prova o mecanismo.

## Rivais obrigatórios

Antes de escolher o teste, liste rivais de tipos diferentes, quando fizerem sentido:
- **olhar o futuro** (dado que só chegou depois, normalização com o período inteiro);
- **seleção** (escolher o melhor de muitos testes, sobrevivência de tokens ou de traders);
- **acaso** (amostra pequena, muitos testes);
- **regime** (vale só num período ou numa volatilidade);
- **custo** (some com taxa, spread, slippage, payout real ou atraso de entrada);
- **artefato de dado** (vela sem negócio, fuso, fonte diferente da corretora);
- **causa comum** (dois sinais que dependem da mesma vela);
- **causalidade invertida** (o sinal reage ao movimento, não o antecede).

## Previsões que diferenciam

Para cada hipótese e rival: em que condição, qual medida, qual padrão esperado, qual resultado a derrubaria, e em que ela difere da rival. Prefira testes em que as explicações preveem coisas diferentes. Inclua controle negativo (placebo, ativo sem relação, atraso de 1 minuto).

## Tipo de afirmação

Declare se a hipótese é descritiva, de associação, de previsão ou causal. No mercado, quase tudo é **associação ou previsão**: não escreva "causa" sem um desenho que permita.

## Registro antes do resultado

Antes de rodar, grave com data no registro do E9: pergunta, hipótese, rivais, previsões, dados (período, ativos, área selada intocada), medida, critério de decisão, número de testes da família. Depois:
- o que surgiu olhando os dados é **exploratório** e precisa de dado novo para confirmar;
- desvios do plano ficam registrados (data, motivo, quem decidiu);
- nunca reescreva uma descoberta como se fosse previsão.

## Fontes

Busca de literatura tem fronteira: registre onde procurou e quando. Diga "não encontrado nesta busca", nunca "não existe". Cite só fonte lida; nota do Vault com natureza `hipotese` ou `nao-verificado` não é evidência.

## Como relatar

Observação (com fonte), hipótese e rivais, previsões, plano registrado (data), resultado com intervalo, o que é confirmatório e o que é exploratório, e o status final (candidata, rejeitada, inconclusiva).

## Crédito

Adaptada de `hypothesis-generation` (v2.4) da K-Dense Inc. ([K-Dense-AI/claude-scientific-skills](https://github.com/K-Dense-AI/claude-scientific-skills), MIT, © 2025). Reescrita para o mercado, sem as partes de biomedicina, os validadores e a instrução de citação. Origem detalhada e avisos de licença em `docs/skills/origens/mneme-hipoteses.md`.
