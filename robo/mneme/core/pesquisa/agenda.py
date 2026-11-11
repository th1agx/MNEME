"""Agenda: em qual braço (par e tempo de aposta) pesquisar agora.

Primeiro todos os braços são tentados um número mínimo de vezes; depois vale um bandido (Thompson) que puxa mais para
onde saem mais promissoras, com um piso de exploração aleatória para nenhum braço ser abandonado por começo ruim.
"""

from __future__ import annotations

import numpy as np

from ...aprendizado import MINUTOS, PARES

BRACOS = tuple((par, minutos) for par in PARES for minutos in MINUTOS)
MINIMO_POR_BRACO = 2
PISO_EXPLORACAO = 0.10


def escolher(estatisticas: dict[tuple[str, int], dict], rng: np.random.Generator) -> tuple[str, int]:
    tentativas = {b: estatisticas.get(b, {}).get("tentativas", 0) for b in BRACOS}
    poucos = [b for b in BRACOS if tentativas[b] < MINIMO_POR_BRACO]
    if poucos:
        menor = min(tentativas[b] for b in poucos)
        candidatos = [b for b in poucos if tentativas[b] == menor]
        return candidatos[int(rng.integers(len(candidatos)))]
    if rng.random() < PISO_EXPLORACAO:
        return BRACOS[int(rng.integers(len(BRACOS)))]
    amostras = [rng.beta(1 + estatisticas[b]["promissoras"], 1 + estatisticas[b]["tentativas"] - estatisticas[b]["promissoras"]) for b in BRACOS]
    return BRACOS[int(np.argmax(amostras))]
