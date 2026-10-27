# MNEME

Bot de copy trading que acompanha os melhores traders do ranking do FOMO.family, avalia cada operação com um score de risco explicável e, conforme o modo escolhido, sugere, simula ou executa compras e vendas em Solana.

> **O código-fonte deste repositório é criptografado** com [git-crypt](https://github.com/AGWA/git-crypt). Ficam abertos este README e a pasta [`docs/`](docs/), com arquitetura, decisões de segurança e operação. Sem a chave, os demais arquivos aparecem como dados binários.

## O que o projeto faz

- **Sinais em tempo real:** recebe os movimentos do Top do ranking por WebSocket, descarta duplicados e recupera o que passou durante quedas de conexão.
- **Score de risco explicável (0–100):** ranking do trader, histórico copiando o trader, consenso entre traders, velocidade do sinal, liquidez, se o preço já disparou e convicção. Cada fator aparece no painel com o motivo.
- **Calibração honesta:** o score não é vendido como probabilidade; o painel mostra a taxa de acerto real por faixa de score, medida nas posições encerradas.
- **Execução em três modos:** só sugestões, carteira simulada com preços reais, ou dinheiro real numa carteira Solana dedicada via Jupiter.
- **Gestão de risco:** tamanho por valor fixo, % do saldo ou % da operação do trader; limites de exposição, por token, de posições e de perda diária; alvo, stop, stop móvel e tempo máximo; saída proporcional à do trader.
- **Painel web e Telegram:** painel em estilo de corretora e comandos pelo celular (`/status`, `/posicoes`, `/pausar`, `/vender`).

## Engenharia

- TypeScript, arquitetura em camadas (portas e adaptadores) com regras de negócio puras e testáveis: [docs/codigo.md](docs/codigo.md).
- Testes automatizados do domínio, do fluxo completo e dos adaptadores externos.
- Docker com reinício automático, checagem de saúde e acesso ao painel por Cloudflare Tunnel + Access: [docs/deploy.md](docs/deploy.md).

## Segurança (blue team)

- **Segredos fora do código:** chaves só no ambiente; dinheiro real exige duas chaves de ativação e confirmação explícita.
- **Defesas na execução:** recusa de ordem antes de assinar se a cotação piorar além do limite; reconciliação pela blockchain quando a resposta do agregador se perde; disjuntor que pausa entradas após falhas seguidas.
- **Superfície mínima:** painel só em `127.0.0.1` por padrão, senha obrigatória quando exposto, proteção contra requisições de outros sites, Telegram restrito a um chat.
- **Confidencialidade do código:** git-crypt com tudo fechado por padrão; ver [docs/criptografia.md](docs/criptografia.md) para gestão e rotação da chave.

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/arquitetura.md](docs/arquitetura.md) | Visão, fontes de dados e plano |
| [docs/codigo.md](docs/codigo.md) | Camadas, fluxo de um sinal, robustez e segurança da execução |
| [docs/design.md](docs/design.md) | Linguagem visual do painel |
| [docs/operacao.md](docs/operacao.md) | Como rodar, modos e roteiro de conexão |
| [docs/deploy.md](docs/deploy.md) | Servidor 24 h, Cloudflare, Telegram e backup |
| [docs/criptografia.md](docs/criptografia.md) | Como o repositório é criptografado e como a chave é gerida |

## Aviso

Projeto pessoal e de estudo. Não é recomendação de investimento: desempenho passado de um ranking não garante resultado futuro, e operar criptoativos pode causar perdas.

© Thiago Antunes. Todos os direitos reservados.
