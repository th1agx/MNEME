"""Liquidação única: onde uma operação entra, onde sai e por quê. Laboratório, backtest, motor e simulado usam estas funções.

Antes (até 11/11/2026) a mesma regra estava escrita em vários lugares. Na expiração fixa os preços coincidiam; no stop e
alvo não: o motor executava o stop no próprio preço do stop mesmo quando a vela abria além dele (gap), o que é otimista,
enquanto o laboratório executava na abertura. A regra honesta, a do laboratório, vale agora para todos.

Convenção de índices: `abertura`, `maxima`, `minima` e `fechamento` são arrays de velas de 1 minuto contínuas (minuto
faltando = NaN). `entrada` é o índice da vela em cuja abertura a operação entra.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ---------------------------------------------------------------- expiração fixa (opções digitais)

@dataclass(frozen=True)
class Digital:
    preco_entrada: float
    preco_saida: float
    resultado: str  # "ganho", "perda" ou "empate"


def liquidar_digital(abertura: np.ndarray, fechamento: np.ndarray, entrada: int, minutos: int, direcao: int) -> Digital | None:
    """Entra na abertura da vela `entrada` e sai no fechamento da última vela do prazo: `minutos` depois da entrada.

    Sem preço em uma das pontas, ou prazo além das velas disponíveis, não apura.
    """
    saida = entrada + minutos - 1
    if entrada < 0 or saida >= len(fechamento):
        return None
    preco_entrada, preco_saida = float(abertura[entrada]), float(fechamento[saida])
    if np.isnan(preco_entrada) or np.isnan(preco_saida):
        return None
    variacao = (preco_saida - preco_entrada) * direcao
    return Digital(preco_entrada, preco_saida, "ganho" if variacao > 0 else "perda" if variacao < 0 else "empate")


def pnl_digital(resultado: str, payout: float, empate: str = "devolve") -> float:
    """Em unidades de aposta. A regra de empate depende da plataforma; o padrão é devolver a aposta."""
    if resultado == "ganho":
        return payout
    if resultado == "perda" or empate == "perde":
        return -1.0
    return 0.0


# ---------------------------------------------------------------- stop, alvo e tempo (posição)

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
