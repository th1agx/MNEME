"""Modalidade de posição: stop, alvo e tempo máximo, com custo do mercado."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComStop:
    """Posição com stop, alvo e tempo máximo. `vende` diz se dá para ficar vendido: à vista só compra. O custo é hipótese até ser medido."""
    custo_bps: float
    stop_atr: float
    alvo_atr: float
    vende: bool
    custo_medido: bool = False
    tipo: str = "com_stop"

    def permite(self, direcao: int) -> bool:
        return direcao == 1 or (direcao == -1 and self.vende)

    def expectativa(self, evidencia: dict) -> float | None:
        """Em unidades de risco (R) por operação, já com o custo desta modalidade."""
        bruto, r_por_bps = evidencia.get("r_bruto"), evidencia.get("r_por_bps")
        return None if bruto is None or r_por_bps is None else bruto - self.custo_bps * r_por_bps
