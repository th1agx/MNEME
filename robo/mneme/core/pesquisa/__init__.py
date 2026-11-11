"""E9 generativo: o MNEME escreve estratégias novas em código, testa numa sandbox e aprende com o resultado.

Diferente do E9 de enumeração (`mneme.aprendizado`), aqui a LLM não escolhe de uma lista: ela escreve uma função
`sinal(v)` inédita. O código passa por uma checagem estática, roda num container sem rede e com limites, é testado
contra olhar o futuro e medido na mesma régua (exploração → confirmação → simulado ao vivo). Tudo vai para o arquivo
de descobertas e falhas, que volta como contexto na próxima geração. Nada aqui opera: quem passa vira candidata e
ainda precisa do simulado ao vivo e da aprovação de uma pessoa.

    python -m mneme.core.pesquisa ciclo
    python -m mneme.core.pesquisa listar
"""
