# Origem e licenças de `mneme-poder-estatistico`

```text
Skill própria do MNEME, adaptada (não copiada) em 08/11/2026.

Fonte (licença MIT, aviso em LICENSE):
K-Dense-AI/claude-scientific-skills, skills/statistical-power/SKILL.md
versão 1.3 (revisada pelo autor em 01/10/2026); sha256 do arquivo lido a969660eafdc3504...
Copyright (c) 2025 K-Dense Inc.

Aproveitado: efeito mínimo que importa em vez de convenção; sem poder calculado depois do resultado;
sensibilidade em faixa; simulação quando a fórmula não cabe; ajustes de múltiplos testes, perdas e
agrupamento (efeito de desenho).

Adaptado: efeito mínimo pela economia da operação (empate do payout, expectativa líquida); amostra
efetiva com operações correlacionadas (exemplo real do diário); correção da família de testes do E9;
contas com scipy e a biblioteca padrão, que já estão no ambiente. Números conferidos: 4.027 e 978
operações para 56% e 58% contra o empate de 54,05% (alfa 5%, poder 80%, unilateral).

Removido: instalação de statsmodels, pingouin e lifelines; exemplos clínicos; scripts; instrução de
citação dos autores.
```

## Avisos de licença das fontes

```text
MIT License

Copyright (c) 2025 K-Dense Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

```
