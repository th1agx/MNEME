# ADR-0016: incorporar Hugin e Munin ao ciclo de notícias do MNEME

**Estado:** Aceita nesta branch, pendente de implantação e validação operacional.

**Contexto:** O MNEME já possui um único serviço de inteligência (`mneme.inteligencia`) que lê feeds, guarda artigos e calcula atributos para o previsor. O filtro e o agrupador do CORVO não devem criar um segundo robô ou ciclo. RSS fornece data de publicação, mas em geral não informa quando ocorreu o fato; usar `pubDate` como `ocorrido_em` ou como hora de chegada permite vazamento temporal. O serviço também não deve automatizar fontes sem permissão compatível com coleta, retenção e uso preditivo.

**Decisão:** Integrar o gate determinístico Hugin e o agrupamento candidato Munin ao ciclo existente de `mneme.inteligencia`. Habilitar somente os feeds oficiais Fed, ECB e BEA, após revisão documentada de termos. Desabilitar feeds editoriais até obter permissão específica e filtrar seus registros legados de atributos, agrupamentos, resumos e interpretação LLM sem apagar o acervo. Persistir `publicado_em` separado, manter `ocorrido_em` nulo quando desconhecido e carimbar `recebido_em` depois de cada download completo. Particionar e filtrar notícias pela hora de recebimento; calcular `n_*` somente com artigos disponíveis no instante consultado. Rotular a origem oficial como publicação institucional, nunca como confirmação automática. Manter suspeitos fora do LLM.

**Consequências:** O previsor pode receber as features `n_*` pelo caminho já existente, sem processo, banco ou API adicional. O agrupamento Munin é candidato de evento: não prova confirmação nem independência das fontes. As novas permissões impedem a coleta automática de sete feeds editoriais previamente configurados. Backfills e classificações históricas continuam limitados pela permissão da fonte e pela disponibilidade de `recebido_em`. A existência de código e testes locais não demonstra implantação, artefato remoto ou ganho preditivo; esses estados serão verificados após o envio/implantação.


O Munin processa candidatos de modo incremental. Associações históricas persistidas ficam congeladas; um item tardio precisa satisfazer as regras contra todos os membros para entrar no grupo, evitando reidentificar ou dividir silenciosamente eventos já gravados.
