"""A0 do E9 v2: a régua travada. É a superfície que o laço de aprendizado nunca altera.

Cada versão é imutável e tem uma impressão. Uma hipótese registra a impressão da régua antes do teste, e quem avalia
recusa uma régua diferente. Mudar um critério é decisão do dono e vira uma versão nova, que vale só para as rodadas seguintes.
Valores da v1 propostos no Plano E9 v2 (Vault, 09-system-knowledge) e aceitos pelo dono em 08/11/2026.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from scipy.stats import norm


class ReguaDiferente(Exception):
    """A régua usada não é a registrada na hipótese: o resultado não vale."""


@dataclass(frozen=True)
class Regua:
    versao: str
    efeito_minimo: float = 0.02  # pontos de acerto acima do empate real que pagam o risco
    alfa: float = 0.05
    correcao: str = "holm"  # sobre a família inteira do mês, contando as rejeitadas
    poder_laboratorio: float = 0.8
    poder_promocao: float = 0.9
    confirmatorias_por_mes: int = 20  # exploratórias são livres, mas não aprovam nada
    atraso_min: int = 1
    walk_forward_purga_embargo: bool = True
    placebo: bool = True
    duas_metades_acima_do_empate: bool = True
    nenhuma_dimensao_critica_piora: tuple[str, ...] = ("ativo", "modalidade", "horizonte", "regime", "periodo")
    area_selada_desde: str = "2026-08-01"
    aberturas_da_area_selada_por_candidato: int = 1
    amostra_efetiva_por: tuple[str, ...] = ("vela", "dia")
    sombra_pareada_antes_de_promover: bool = True
    promocao_e_rollback: str = "dono"

    def impressao(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]


REGUAS = {"v1": Regua("v1")}
ATUAL = "v1"


def conferir(impressao_registrada: str, regua: Regua) -> None:
    if regua.impressao() != impressao_registrada:
        raise ReguaDiferente(f"régua {regua.versao} ({regua.impressao()}) diferente da registrada ({impressao_registrada})")


def empate(payout: float) -> float:
    """Acerto que zera a expectativa na expiração fixa, sem contar empates."""
    return 1 / (1 + payout)


def n_necessario(p_real: float, p_empate: float, alfa: float, poder: float) -> float:
    """Operações independentes para detectar `p_real` contra o empate, teste de um lado."""
    za, zb = norm.ppf(1 - alfa), norm.ppf(poder)
    return ((za * (p_empate * (1 - p_empate)) ** 0.5 + zb * (p_real * (1 - p_real)) ** 0.5) / (p_real - p_empate)) ** 2


def amostra_minima(regua: Regua, payout: float, familia: int, promocao: bool = False) -> int:
    """Amostra efetiva mínima para o efeito mínimo da régua, com o alfa corrigido (Bonferroni, o pior caso do Holm)."""
    e = empate(payout)
    poder = regua.poder_promocao if promocao else regua.poder_laboratorio
    return int(n_necessario(e + regua.efeito_minimo, e, regua.alfa / max(familia, 1), poder) + 0.999)


def holm(pvalores: list[float]) -> list[float]:
    """Valores-p ajustados de Holm, na ordem de entrada."""
    m = len(pvalores)
    ordem = sorted(range(m), key=lambda i: pvalores[i])
    ajustados, maior = [0.0] * m, 0.0
    for posicao, i in enumerate(ordem):
        maior = max(maior, min(1.0, (m - posicao) * pvalores[i]))
        ajustados[i] = maior
    return ajustados
