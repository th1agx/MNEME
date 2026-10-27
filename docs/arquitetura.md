# Projeto: Agente de Copy Trading para FOMO.family

**Documento de visão, arquitetura e plano de implementação**\
**Data:** 27 de outubro de 2026\
**Status:** Proposta técnica --- integração ainda precisa ser validada

## 1. Resumo executivo

A proposta é desenvolver uma aplicação que acompanhe o ranking de
traders do FOMO.family --- inicialmente os cinco primeiros do ranking de
24 horas --- detecte compras, vendas e teses publicadas por esses
traders e apresente os eventos em um dashboard. Em uma etapa posterior,
o sistema poderá replicar operações em uma carteira própria, conforme
regras de risco explícitas.

O objetivo é reduzir o tempo entre a movimentação observada e a decisão
do usuário, sem prometer execução no mesmo instante. Atrasos de captura,
rede, confirmação, liquidez, slippage, taxas e falhas de cobertura podem
fazer com que a ordem replicada tenha preço e resultado diferentes da
operação original.

**Princípio central:** usar código determinístico para captura,
validação, regras de risco e execução. A IA generativa deve explicar e
analisar os dados, não ter liberdade irrestrita para movimentar fundos.

## 2. Escopo funcional

### MVP --- primeira versão

-   Consultar um ranking escolhido (24h, 7d ou 30d) por meio de um
    fornecedor de dados validado.
-   Selecionar e acompanhar os cinco primeiros traders, com registro das
    mudanças no Top 5.
-   Receber eventos de compra, venda e tese, quando disponíveis na
    fonte.
-   Mostrar trader, ação, token, rede, valor, horário do evento, horário
    de recebimento e origem do dado.
-   Deduplicar eventos e registrar desconexões, erros e eventos
    incompletos.
-   Executar paper trading: simular a ordem com preço de mercado
    observável, taxas e slippage configuráveis.
-   Dashboard com status da conexão, feed ao vivo, traders acompanhados,
    atraso medido, ordens simuladas e histórico.
-   Modo de alertas com aprovação manual.
-   Botão de pausa para impedir novas simulações/ordens.

### Fora do escopo inicial

-   Executar operações reais sem testes de qualidade de dados.
-   Prometer copiar a operação no mesmo segundo.
-   Permitir que um LLM escolha livremente o valor ou assine transações.
-   Armazenar a chave privada da carteira principal.
-   Assumir que ranking, lucro publicado ou tese de um trader garantem
    rentabilidade futura.

## 3. Fonte de dados e integração

O FOMO.family apresenta rankings, feed, traders seguidos e notificações.
Entretanto, as fontes públicas consultadas não confirmam uma API pública
oficial de desenvolvedor do próprio FOMO.family. Portanto, não se deve
presumir que seja possível integrar diretamente ao backend privado do
site de forma estável ou autorizada.

Opções de integração a avaliar:

### Opção A --- FOMOAPI (`fomoapi.io`)

Documentação: https://fomoapi.io/docs\
Site: https://fomoapi.io/

A documentação descreve dois fluxos WebSocket: - **Feed da aplicação
(`/ws/alerts`)**: eventos publicados pelo feed, incluindo compras,
vendas e teses, sujeitos ao momento em que o sistema de origem publica e
o provedor captura. - **Eventos on-chain (`/ws/trades`)**: transações
detectadas nas redes suportadas, com hash e tamanho real quando
disponíveis. A cobertura depende da atribuição correta de carteiras e da
ingestão da rede; não garante todas as operações de todos os traders.

A documentação informa que o stream on-chain pode chegar antes do feed
do aplicativo em medições históricas específicas, mas isso não é uma
garantia de latência. Confirmar preços, planos, limites, autenticação,
cobertura e termos antes de escolher.

### Opção B --- FomoAPI (`fomoapi.family`)

Documentação: https://fomoapi.family/reference\
A documentação descreve endpoints REST para perfis, rankings, tokens e
teses, além de WebSocket em `/ws/alerts` para eventos de traders
acompanhados. A própria documentação informa que a conexão é cobrada em
créditos e exige plano com acesso a realtime. Validar o fornecedor,
custos e cobertura em um teste real.

### Opção C --- FOMO Glass

Site: https://fomo.glass/

A plataforma declara acompanhar traders escolhidos, exibir
compras/vendas em tempo real e oferecer um WebSocket próprio em plano
Unlimited para integrar software externo. Ela se apresenta como tracker,
não como executor de operações. Confirmar condições, preço, autenticação
e formato do stream antes da implementação.

### Opção D --- observação do site no navegador

Só usar se houver autorização e se os termos do serviço permitirem.
Automação visual é frágil: mudanças no HTML, login, notificações,
CAPTCHA, sessão expirada ou atualização de layout podem interromper o
monitoramento. Não contornar autenticação, controles de acesso ou
proteções. Preferir API/stream documentado de fornecedor independente.

### Recomendação

Começar com uma prova de conceito comparando ao menos uma fonte de
eventos com a página/feed visível. Registrar timestamps e medir
cobertura/atraso. Não codificar o sistema inteiro em torno de endpoint
privado ou não documentado.

## 4. Arquitetura proposta

``` mermaid
flowchart TD
    A[FOMO.family / ranking e feed] --> B[Fornecedor de dados autorizado]
    B --> C[Conector REST + WebSocket]
    C --> D[Validação do esquema e normalização]
    D --> E[Deduplicação e idempotência]
    E --> F[Persistência PostgreSQL]
    E --> G[Verificação on-chain quando possível]
    F --> H[Motor determinístico de regras]
    G --> H
    H --> I[Paper trading]
    H --> J[Alertas e aprovação manual]
    H -. etapa posterior, autorizada .-> K[Executor de ordens isolado]
    K --> L[Carteira dedicada / exchange]
    F --> M[API do dashboard]
    H --> M
    I --> M
    M --> N[Dashboard Next.js]
    F --> O[Agente LLM para relatórios]
    O --> M
```

### Componentes

1.  **Conector de fonte:** autentica, conecta ao WebSocket, aplica
    filtros por trader/rede/tipo e reconecta com backoff.
2.  **Normalizador:** converte formatos de fornecedores para um esquema
    interno comum.
3.  **Deduplicador:** usa ID do evento e, quando aplicável, hash da
    transação + log/índice. Impede que reconexões e replays criem ordens
    duplicadas.
4.  **Verificador:** consulta dados on-chain para conferir transação,
    token, rede e estado quando disponíveis.
5.  **Motor de regras:** decide se o evento é elegível; não usa LLM para
    controles financeiros críticos.
6.  **Simulador:** calcula quantidade hipotética, preço disponível,
    taxas, slippage, saldo simulado e PnL.
7.  **Executor futuro:** serviço isolado, com autorização explícita,
    carteira dedicada, limites rígidos e logs de auditoria.
8.  **Dashboard:** apresenta estado, feed, latência, ranking,
    simulações, erros, regras e pausa.
9.  **Agente de IA:** resume padrões e explica relatórios a partir de
    dados armazenados, sem receber chaves privadas.

## 5. Stack recomendada

  -----------------------------------------------------------------------
  Camada                  Escolha sugerida        Motivo
  ----------------------- ----------------------- -----------------------
  Linguagem principal     TypeScript              Tipos compartilhados
                                                  entre backend e
                                                  frontend

  Frontend                Next.js + React         Dashboard e páginas de
                                                  configuração

  Backend                 Node.js + TypeScript    WebSockets, REST e
                          (Fastify ou NestJS)     serviços assíncronos

  Validação               Zod ou JSON Schema      Validar payloads de
                                                  fornecedores

  Banco                   PostgreSQL              Histórico, auditoria,
                                                  traders, eventos e
                                                  simulações

  Cache/fila opcional     Redis + BullMQ          Reprocessamento e
                                                  tarefas assíncronas
                                                  quando necessário

  Tempo real no dashboard WebSocket ou            Atualizar o feed sem
                          Server-Sent Events      polling constante

  Observabilidade         Pino + OpenTelemetry,   Diagnóstico de atraso,
                          métricas e alertas      falhas e desconexões

  Testes                  Vitest + testes de      Normalização,
                          integração              idempotência e regras
                                                  de risco

  Deploy inicial          Docker Compose em       Simplicidade; evitar
                          VPS/serviço gerenciado  Kubernetes no MVP
  -----------------------------------------------------------------------

Não introduzir Redis/fila até haver uma necessidade demonstrada. Para o
primeiro MVP, backend + PostgreSQL podem ser suficientes.

## 6. Qual agente de IA usar?

### Para desenvolver o software

-   **Codex ou Claude Code:** podem ajudar a implementar o repositório,
    escrever testes, documentar integrações e revisar código. A escolha
    deve considerar o ambiente de desenvolvimento, as permissões
    concedidas e a qualidade dos testes.
-   Use o agente de programação com acesso restrito ao repositório e sem
    credenciais de produção. Exija revisão humana antes de deploy.

### Para o agente em produção

Um LLM via API pode: - resumir o comportamento de traders; - explicar
mudanças de padrão; - produzir relatórios diários; - responder perguntas
sobre o histórico armazenado.

Não é recomendável colocar um LLM no caminho crítico de cada ordem.
Latência, custo, respostas não determinísticas e risco de interpretar
mal o evento tornam esse desenho inadequado para executar dinheiro
automaticamente. O processamento de eventos e a autorização de ordens
devem seguir regras explícitas e testáveis.

## 7. Modelo de evento interno

Normalizar cada evento para um formato semelhante a:

``` json
{
  "event_id": "id-estavel-do-fornecedor",
  "source": "nome-do-fornecedor",
  "trader_handle": "handle",
  "event_type": "swap_buy",
  "chain": "solana",
  "token_address": "endereco-do-token",
  "token_symbol": "TOKEN",
  "amount_usd": 100.0,
  "transaction_hash": null,
  "event_time": "2026-10-27T15:00:00Z",
  "received_at": "2026-10-27T15:00:02Z",
  "thesis_text": null,
  "verification_status": "pending"
}
```

Os valores acima são apenas exemplo de esquema, não dados reais. Campos
desconhecidos devem permanecer `null`; não inferir endereço, valor ou
horário ausentes. Armazenar timestamps em UTC e exibir no fuso local do
usuário.

## 8. Fluxo de processamento

1.  Carregar ranking para o período escolhido.
2.  Atualizar a lista Top 5 em intervalo configurado e registrar
    entradas/saídas.
3.  Manter assinatura do feed para os traders selecionados.
4.  Receber e validar o evento.
5.  Deduplicar antes de gerar qualquer ação.
6.  Conferir rede, contrato do token e transação quando possível.
7.  Calcular atraso: `received_at - event_time`, lembrando que o horário
    de origem pode ser publicação do feed e não o horário exato da
    execução on-chain.
8.  Aplicar regras de elegibilidade e risco.
9.  Em MVP, simular ordem usando preço disponível e registrar o
    resultado.
10. Enviar atualização ao dashboard e, se ativado, notificação.
11. Registrar falhas, reconexões e eventos descartados com motivo.

## 9. Regras de risco obrigatórias

Antes de habilitar dinheiro real: - Limite máximo por ordem e por
trader. - Limite de exposição total e perda diária. - Lista de redes e
tokens permitidos. - Proteção contra token/contrato desconhecido,
liquidez insuficiente e slippage excessivo. - Verificação de saldo e
taxas. - Idempotência para não repetir a mesma ordem. - Pausa imediata e
disjuntor em caso de feed atrasado, erros de execução ou perda de
conexão. - Aprovação explícita do usuário para habilitar o modo real. -
Logs de auditoria sem segredos. - Carteira dedicada, com fundos
limitados; nunca enviar seed phrase ou chave privada a um LLM ou serviço
de terceiros.

Uma venda do trader não significa necessariamente que o sistema deva
vender exatamente a mesma quantidade: pode haver compras parciais,
posições anteriores diferentes, saldo insuficiente ou impossibilidade de
executar. Essa política precisa ser definida e testada.

## 10. Dashboard --- telas previstas

-   **Visão geral:** estado da conexão, modo ativo, traders monitorados,
    eventos, latência e alertas.
-   **Traders:** ranking por período, seleção de Top 5, mudança de
    posição e filtros.
-   **Feed ao vivo:** compra/venda/tese, token, rede, valor, horário de
    origem e recebimento.
-   **Simulações:** sinal, preço de referência, preço simulado, taxas,
    slippage e PnL.
-   **Regras:** valor máximo, exposição, slippage, perda diária,
    tokens/rede permitidos.
-   **Auditoria:** eventos recebidos, duplicados, descartados, falhas e
    ordens.
-   **Controles:** simulação, alertas, pausa e futura ativação explícita
    do modo real.

## 11. Plano de implementação

### Fase 0 --- validar fonte (1--3 dias, estimativa)

-   Comparar fornecedor, documentação, preço, autenticação, termos e
    cobertura.
-   Confirmar se os eventos incluem compra, venda e tese.
-   Medir latência e perdas com um trader de teste.
-   Verificar como o ranking Top 5 é obtido e atualizado.

### Fase 1 --- dashboard e esquema (3--5 dias, estimativa)

-   Criar app Next.js e backend TypeScript.
-   Criar tabelas e contrato de evento.
-   Alimentar a interface com dados simulados.

### Fase 2 --- captura ao vivo (3--7 dias, estimativa)

-   Implementar WebSocket, reconexão, filtros e deduplicação.
-   Persistir eventos e medir latência.
-   Criar métricas e testes de integração.

### Fase 3 --- paper trading (3--7 dias, estimativa)

-   Definir política de replicação.
-   Simular preços, taxas, slippage, falhas e saídas.
-   Comparar resultado simulado com o resultado possível em condições
    realistas.

### Fase 4 --- revisão para execução real

-   Revisar segurança, termos, riscos e qualidade dos dados.
-   Escolher integração de negociação por rede.
-   Implementar executor isolado, carteira dedicada, limites e aprovação
    explícita.
-   Liberar gradualmente com valores pequenos, se o usuário decidir
    prosseguir.

As estimativas são aproximadas para uma pessoa com experiência e
dependem do fornecedor e da documentação disponível.

## 12. Critérios de aceite do MVP

-   Eventos válidos aparecem no dashboard com origem e timestamps.
-   Eventos repetidos não geram simulações duplicadas.
-   Desconexões são detectadas e reconexões registradas.
-   A latência é medida e exibida, sem promessa de tempo fixo.
-   O Top 5 e suas mudanças ficam registrados.
-   O simulador considera taxas e slippage configuráveis.
-   Nenhuma ordem real pode ser enviada no modo de simulação.
-   Existe trilha de auditoria para eventos processados e descartados.

## 13. Links para investigação

-   FOMO.family: https://fomo.family/
-   FOMOAPI.io --- documentação: https://fomoapi.io/docs
-   FOMOAPI.io --- preços: https://fomoapi.io/pricing
-   FomoAPI.family --- referência: https://fomoapi.family/reference
-   FOMO Glass: https://fomo.glass/
-   Foma --- documentação de copy trading: https://tradefoma.family/docs

**Nota de independência:** FOMOAPI.io, FomoAPI.family, FOMO Glass e Foma
são serviços de terceiros. A existência de documentação não implica
afiliação, endosso ou garantia do FOMO.family. Verifique os termos, a
segurança, os preços e a disponibilidade atual diretamente com cada
fornecedor.

## 14. Decisões pendentes

1.  Qual fornecedor será usado após o teste?
2.  Qual rede será suportada primeiro (Solana, Base ou outra)?
3.  O Top 5 será baseado em PnL de 24h, 7d ou outro critério?
4.  O sistema copia valores fixos, proporção do valor do trader ou outra
    regra?
5.  O que fazer quando o trader vende parcialmente, muda de ranking ou
    um evento chega atrasado?
6.  Qual limite de capital e perda será permitido na eventual fase real?

Até essas decisões e os testes de latência serem concluídos, o sistema
deve permanecer em simulação ou alertas manuais.
