"""Ponto único de entrada da liquidação dos dois domínios. As regras ficam em cada domínio:

- opções digitais (expiração fixa): `mneme.digitais.liquidacao`;
- posições com stop, alvo e tempo: `mneme.mercados.liquidacao`.
"""

from .digitais.liquidacao import Digital, liquidar_digital, pnl_digital
from .mercados.liquidacao import Posicao, liquidar_posicao

__all__ = ["Digital", "Posicao", "liquidar_digital", "liquidar_posicao", "pnl_digital"]
