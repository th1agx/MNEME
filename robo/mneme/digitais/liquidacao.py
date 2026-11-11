"""Liquidação de opções digitais (CALL/PUT com expiração fixa). Laboratório, backtest, motor e simulado usam esta regra.

Convenção: `abertura` e `fechamento` são arrays de velas de 1 minuto contínuas (minuto faltando = NaN). `entrada` é o
índice da vela em cuja abertura a operação entra.

Fidelidade: com velas de referência (Binance, Dukascopy) isto é uma aproximação. Cada plataforma tem a própria cotação,
o próprio arredondamento e a própria regra de empate; esses dados entram pelos adaptadores de plataforma.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
