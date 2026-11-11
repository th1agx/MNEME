"""Modalidade de opção digital: CALL ou PUT com prazo definido, payout por operação."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpiracaoFixa:
    """CALL ou PUT com prazo definido. Sem stop e sem alvo. O payout é hipótese até ser medido na corretora."""
    payout: float
    payout_medido: bool = False
    tipo: str = "expiracao_fixa"

    @property
    def empate(self) -> float:
        return 1 / (1 + self.payout)

    def permite(self, direcao: int) -> bool:
        return direcao in (1, -1)

    def expectativa(self, evidencia: dict) -> float | None:
        """Em unidades de aposta por operação: ganha o payout ou perde a aposta inteira."""
        acerto = evidencia.get("acerto")
        return None if acerto is None else acerto * self.payout - (1 - acerto)
