"""Liquidação de posições com stop, alvo e tempo. Laboratório, backtest, motor e simulado usam esta regra.

Até 11/11/2026 o motor executava o stop no próprio preço do stop mesmo quando a vela abria além dele (gap), o que é
otimista; o laboratório executava na abertura. A regra honesta, a do laboratório, vale agora para todos.

Convenção: arrays de velas de 1 minuto contínuas (minuto faltando = NaN). `entrada` é o índice da vela em cuja abertura
a operação entra. Custos ficam com quem chama: cada mercado tem os seus (taxa, spread, funding).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Posicao:
    preco_entrada: float
    preco_saida: float
    motivo: str  # "stop", "alvo" ou "tempo"
    saida: int  # índice da vela em que saiu


def liquidar_posicao(abertura: np.ndarray, maxima: np.ndarray, minima: np.ndarray, fechamento: np.ndarray, entrada: int,
                     velas_max: int, lado: int, distancia_stop: float, distancia_alvo: float) -> Posicao | None:
    """Três barreiras a partir da entrada real: stop, alvo e tempo (`velas_max` velas, contando a da entrada).

    - Vela que abre além do stop sai na abertura: é o preço que de fato existia (gap).
    - Stop e alvo na mesma vela: vale o stop. Dentro do minuto não dá para saber a ordem, e o pior caso é o honesto.
    - Sem stop nem alvo, sai no fechamento da última vela do prazo. Se o prazo ainda não terminou nas velas disponíveis
      e nenhuma barreira foi tocada, não apura (o resultado ainda não existe).
    """
    ultimo = entrada + velas_max - 1
    if entrada < 0 or entrada >= len(abertura) or not distancia_stop > 0 or np.isnan(abertura[entrada]):
        return None
    preco_entrada = float(abertura[entrada])
    stop, alvo = preco_entrada - lado * distancia_stop, preco_entrada + lado * distancia_alvo
    for j in range(entrada, min(ultimo, len(abertura) - 1) + 1):
        if np.isnan(maxima[j]):
            continue
        if (lado > 0 and abertura[j] <= stop) or (lado < 0 and abertura[j] >= stop):
            return Posicao(preco_entrada, float(abertura[j]), "stop", j)
        if (minima[j] <= stop) if lado > 0 else (maxima[j] >= stop):
            return Posicao(preco_entrada, float(stop), "stop", j)
        if (maxima[j] >= alvo) if lado > 0 else (minima[j] <= alvo):
            return Posicao(preco_entrada, float(alvo), "alvo", j)
    if ultimo >= len(fechamento) or np.isnan(fechamento[ultimo]):
        return None
    return Posicao(preco_entrada, float(fechamento[ultimo]), "tempo", ultimo)
