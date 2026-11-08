"""A1 do E9 v2: onde o robô acerta e onde erra, por dimensão. Descritivo e exploratório: gera perguntas, não conclusões.

Cada recorte mostra a amostra de verdade (velas e dias distintos, porque decisões na mesma vela e no mesmo dia não são
independentes), o intervalo de 95% sorteando dias inteiros e a expectativa por unidade já com o payout. Um recorte só vira
pergunta para o E9 se tiver amostra; virar melhoria exige hipótese registrada antes e o teste na régua travada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..laboratorio.robustez import intervalo_por_dias
from ..laboratorio.validacao import intervalo_wilson
from .regua import ATUAL, REGUAS, Regua, amostra_minima

DIMENSOES = ("estrategia", "ativo", "tipo", "horizonte", "faixa_hora", "dia_semana", "vol_quintil", "forca_quintil", "noticia", "motivo_recusa")


def _leitura(g: pd.Series, minimo: int) -> str:
    if g["velas"] < minimo:
        return "amostra insuficiente"
    if g["ic95_baixo"] > g["empate"]:
        return "acima do empate (exploratório)"
    if g["ic95_alto"] < g["empate"]:
        return "abaixo do empate (exploratório)"
    return "indistinguível do empate"


def atribuir(x: pd.DataFrame, dimensao: str, regua: Regua | None = None) -> pd.DataFrame:
    """Uma linha por valor da dimensão. A amostra efetiva usada na leitura é o número de velas distintas por ativo."""
    regua = regua or REGUAS[ATUAL]
    linhas = []
    for valor, g in x.groupby(x[dimensao].fillna("sem dado") if dimensao in x else pd.Series("sem dado", index=x.index), sort=True):
        r = g[g["ganho"].notna()]
        acertos, n = int(r["ganho"].sum()), len(r)
        if n:
            dias = intervalo_por_dias(r["ganho"].to_numpy(), pd.DatetimeIndex(r["vela"]))
            wilson = intervalo_wilson(acertos, n)
            baixo, alto = min(dias[0], wilson[0]), max(dias[1], wilson[1])  # o mais largo dos dois: nunca o mais otimista
        else:
            baixo = alto = np.nan
        linhas.append({"dimensao": dimensao, "valor": valor, "decisoes": len(g), "com_resultado": n, "empates": int((g["resultado"] == "empate").sum()),
                       "velas": int(r[["ativo", "vela"]].drop_duplicates().shape[0]), "dias": int(r["dia"].nunique()),
                       "acerto": acertos / n if n else np.nan, "ic95_baixo": baixo, "ic95_alto": alto, "empate": float(g["empate"].mean()),
                       "expectativa_por_unidade": float(g["pnl_por_unidade"].mean()), "resultado_total": float(g["pnl"].sum())})
    tabela = pd.DataFrame(linhas)
    if tabela.empty:
        return tabela
    payout = float(x["payout"].dropna().median()) if x["payout"].notna().any() else 0.85
    minimo = amostra_minima(regua, payout, familia=1)
    tabela["leitura"] = tabela.apply(_leitura, axis=1, minimo=minimo)
    return tabela


def resumo(x: pd.DataFrame, dimensoes: tuple[str, ...] = DIMENSOES, regua: Regua | None = None) -> dict[str, pd.DataFrame]:
    return {d: atribuir(x, d, regua) for d in dimensoes}
