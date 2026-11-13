# Knowledge Engine: RAG e inteligência de notícias

**Situação:** referência de arquitetura, subordinada ao [Product Charter](../PRODUCT_CHARTER.md). O estado real está em [RASTREABILIDADE.md](RASTREABILIDADE.md).

## Dois sistemas, um limite

- **Base de conhecimento (RAG):** livros, artigos, conceitos, estudos. Muda devagar e serve para **formular hipóteses e explicar**.
- **Notícias e eventos:** fatos datados, que mudam a cada minuto. Viram **atributos e evidências**, com hora.

Nenhum dos dois treina modelo de previsão nem decide operação. O RAG responde "o que se sabe sobre isso"; se funciona, quem diz é o laboratório.

## Pipeline de ingestão

```mermaid
flowchart LR
    A[Documento] --> B[Hash e deduplicação]
    B --> C[Extração de texto]
    C --> D[Tema e categoria]
    D --> E[Conceitos]
    E --> F[Trechos]
    F --> G[Embeddings locais]
    G --> H[(pgvector)]
    C --> I[(Original privado)]
    E --> J[Catálogo de hipóteses]
```

| Etapa | Como |
|---|---|
| Receber | Pasta de entrada ou comando; formatos PDF, Markdown, texto. Anotações e exemplos de operações entram como documentos do dono |
| Extrair | Extrator de PDF; livro escaneado passa por OCR, com qualidade registrada |
| Classificar | Por categoria: indicadores, fluxo, macro, risco, estudo, setup, com o LLM local em lotes fora dos horários de maior uso |
| Conceitos | Extrai regra, condição de uso e limitação |
| Embeddings | `fastembed`, em CPU e local, com modelo multilíngue a validar |
| Armazenar | Postgres + pgvector, com índice HNSW |
| Origem | Documento, página, data, versão, confiabilidade |
| Recuperar | Busca vetorial + texto (`tsvector`) + filtros por categoria, mercado e data |

### Modelo de dados

```text
documentos(id, hash, titulo, autor, tipo, publicado_em, ingerido_em, versao, licenca, confiabilidade, caminho_original)
trechos(id, documento_id, pagina, ordem, texto, embedding, categoria, mercados[])
hipoteses(id, documento_id, trecho_id, regra, condicoes, limitacoes, situacao, experimento_id)
```

`hipoteses.situacao` vai de "não testada" até "aprovada" ou "reprovada", ligada ao experimento. Assim, o RAG responde com o resultado medido ao lado da teoria.

### Consulta contextual

Para "quais estratégias se aplicam com BTC acima da VWAP, RSI em 68 e volume crescente?":

1. Lê os valores reais do momento nos atributos e confere a pergunta com eles.
2. Busca trechos e hipóteses que combinam com o estado.
3. Junta o resultado medido de cada hipótese, por mercado e regime.
4. Responde com fontes, deixando claro o que foi testado e o que não foi.

### Direitos e privacidade

Só entra material legalmente disponível ao dono. Originais e índice ficam na A1, **fora do repositório**. Respostas citam trechos curtos e nunca reproduzem a obra. Em `robo/conhecimento/` continuam só resumos próprios, com fontes.

### Áreas iniciais

Price Action, Smart Money Concepts, Wyckoff, Elliott Wave, Volume Spread Analysis, Market Profile, Order Flow, trend following, reversão à média, momentum, trading quantitativo, arbitragem estatística, gestão de risco e de portfólio, macro e operações em eventos.

Cada método vira regra testável. Quando a regra é subjetiva e não pode ser escrita (alguns usos de Elliott Wave, por exemplo), ela é marcada como **não testável** e não gera sinal. Nada funciona só porque está num livro ou foi usado por alguém famoso.

## Inteligência de notícias

### Fontes iniciais

| Fonte | Uso | Situação medida em 05/11/2026 |
|---|---|---|
| RSS do Federal Reserve, ECB e BEA | Títulos, resumos curtos, links e datas de comunicados oficiais | Habilitados no coletor após revisão de termos; política e limites em [NEWS_SOURCES.md](../sources/NEWS_SOURCES.md) |
| Bloomberg, Financial Times, CNBC, CoinDesk, The Block, Decrypt e Cointelegraph | Fontes editoriais avaliadas para notícias de mercado | Desabilitadas até confirmar permissão compatível com coleta automatizada, retenção e uso preditivo; ver [NEWS_SOURCES.md](../sources/NEWS_SOURCES.md) |
| Redes sociais | Narrativa | Sem fonte gratuita definida; |
| Calendário econômico | Agenda, consenso e surpresa | Agendas oficiais acessíveis; ver [MARKET_DATA_ENGINE](MARKET_DATA_ENGINE.md) e [ADR-0014](ADR/0014-calendario-economico.md) |

O `mneme.inteligencia` é o único serviço de coleta de notícias e consulta cada feed habilitado a cada cinco minutos. O Hugin integrado ao coletor faz a admissão determinística; o Munin anota candidatos a eventos e a disponibilidade do grupo sem declarar confirmação ou independência. Não há um segundo processo CORVO, API de coleta ou banco separado. Texto RSS é conteúdo não confiável: títulos suspeitos são guardados para auditoria, mas não são enviados ao LLM.

O contrato temporal dos artigos RSS é `publicado_em` (data informada pela fonte), `recebido_em` (primeira leitura pelo MNEME) e `ocorrido_em` (nulo se a fonte não identifica o instante do fato). Features `n_*` usam somente `recebido_em` e ignoram registros sem hora de recebimento; o previsor consulta artigos em corte point-in-time. O mesmo caminho de atributos é usado no treino e na previsão ao vivo, quando o manifesto do modelo solicita as colunas `n_*`.

### Etapas da análise de notícias

| # | Etapa | Executor | Saída |
|---|---|---|---|
| 1 | Ler feed permitido | `mneme.inteligencia` | Artigo com fonte, `publicado_em` e `recebido_em` |
| 2 | Admitir ou descartar | Hugin determinístico | Motivo, relevância e temas candidatos |
| 3 | Agrupar cobertura | Munin determinístico | Candidato com disponibilidade pela chegada mais tardia |
| 4 | Calcular atenção | Atributos `n_*` | Menções, anomalia, sentimento, fontes, concentração e rumor |
| 5 | Prever | Modelo de ML que declara as colunas `n_*` | Probabilidade e incerteza medidas |
| 6 | Interpretar contexto | LLM + RAG, quando chamado pelo leitor | Explicação assíncrona, sem autoridade de decisão |

### Tipos de informação

O coletor distingue **publicação institucional**, reportagem, informação preliminar, rumor, opinião, previsão e especulação. A identidade de uma fonte oficial não confirma afirmações de terceiros nela citadas. O pipeline não cria `fato confirmado` automaticamente: confirmação e independência exigem evidência própria. Rumor e opinião não geram operação sozinhos; uma notícia isolada nunca vira certeza de movimento.

### Exemplo hipotético

Um candidato assume a liderança inesperadamente numa apuração.

1. O sistema detecta e confirma em mais de uma fonte: **fato confirmado** sobre a apuração, e não sobre o resultado final.
2. Mede a surpresa contra as pesquisas anteriores, quando disponíveis.
3. Consulta como o dólar e o índice reagiram em eventos parecidos, com poucos casos e a incerteza declarada.
4. Olha o que o preço já fez. Se o dólar já caiu 1% em minutos, grande parte do efeito pode já estar no preço.
5. Com poucos eventos comparáveis, **a amostra é pequena demais para uma probabilidade calibrada**. Saída provável: aviso informativo, sem operação, ou sinal só se uma estratégia de eventos já estiver promovida.

Em retrospectiva, um movimento sempre parece óbvio. O teste correto é saber se a regra, escrita **antes**, ganharia em todos os casos parecidos, inclusive naqueles em que o mercado fez o oposto.

### Estudo de eventos

É o que transforma notícia em conhecimento medido: para cada tipo de evento, mede o retorno anormal antes e depois, em várias janelas, com grupo de comparação e correção por múltiplos testes. O resultado alimenta as etapas 6 e 9. Correlação não é tratada como causa: o relatório diz o que foi observado e quantos casos sustentam.

## Segurança

- Texto externo é dado, nunca instrução.
- Nós de LLM não têm ferramentas de ordem nem segredos.
- Saída fora do esquema é descartada.
- Nenhum dado identifica a fonte de sinais em prompts, logs visíveis ou respostas.
