"""G0: o placar incremental. Compara qualquer política de apostas com a referência (o motor atual) nas mesmas entradas.

Uma política é uma tabela de apostas: (ativo, tempo, direção) com o retorno da operação pela convenção do motor
(entra na abertura um minuto depois da vela seguinte ao sinal e sai `expiracao` minutos depois). Direção 0 é abster.
O placar mede o que importa para a operação: acerto, expectativa líquida em vários payouts e queda máxima. Os intervalos
sorteiam blocos (dia × ativo), porque apostas do mesmo dia e do mesmo ativo andam juntas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from ..laboratorio.confluencia import ATRASO
from ..laboratorio.horizontes import retorno_da_operacao

PAYOUTS = (0.75, 0.80, 0.85, 0.90)


def apostas(ativo: str, v: pd.DataFrame, tempos: pd.DatetimeIndex, direcao: np.ndarray, expiracao: int, atraso: int = ATRASO) -> pd.DataFrame:
    """A tabela de apostas de uma política num ativo. `tempos` são os minutos de 1 min em que o sinal foi dado."""
    return pd.DataFrame({"ativo": ativo, "tempo": pd.DatetimeIndex(tempos), "direcao": np.asarray(direcao, dtype=float),
                         "retorno": retorno_da_operacao(v, pd.DatetimeIndex(tempos), atraso, expiracao)}).dropna(subset=["retorno"])


def pnl_digital(direcao: np.ndarray, retorno: np.ndarray, payout: float) -> np.ndarray:
    """Expiração fixa por unidade apostada: ganha o payout, perde 1, empata 0; abster vale 0."""
    lado = np.sign(direcao) * np.sign(retorno)
    return np.where(direcao == 0, 0.0, np.where(lado > 0, payout, np.where(lado < 0, -1.0, 0.0)))


def intervalo_por_blocos(valores: np.ndarray, blocos: np.ndarray, sorteios: int = 2000, semente: int = 0) -> tuple[float, float]:
    """Intervalo de 95% da média, sorteando blocos inteiros com reposição."""
    tabela = pd.DataFrame({"b": blocos, "s": valores, "n": 1.0}).groupby("b")[["s", "n"]].sum().to_numpy()
    if len(tabela) < 2:
        return float("nan"), float("nan")
    escolhidos = np.random.default_rng(semente).integers(0, len(tabela), (sorteios, len(tabela)))
    somas = tabela[escolhidos].sum(axis=1)
    medias = somas[:, 0] / somas[:, 1]
    return float(np.quantile(medias, 0.025)), float(np.quantile(medias, 0.975))


def _blocos(a: pd.DataFrame) -> np.ndarray:
    return (a["ativo"].astype(str) + "|" + pd.DatetimeIndex(a["tempo"]).floor("D").astype(str)).to_numpy()


def placar(a: pd.DataFrame, payouts: tuple[float, ...] = PAYOUTS) -> dict:
    a = a.sort_values("tempo")
    operadas = a[a["direcao"] != 0]
    lado = np.sign(operadas["direcao"]) * np.sign(operadas["retorno"])
    com_resultado = lado != 0
    ganhos = (lado[com_resultado] > 0).astype(float).to_numpy()
    blocos = _blocos(operadas)
    saida = {"apostas": int(len(operadas)), "com_resultado": int(com_resultado.sum()), "blocos": int(len(set(blocos))),
             "acerto": float(ganhos.mean()) if len(ganhos) else float("nan"),
             "acerto_ic95": intervalo_por_blocos(ganhos, blocos[com_resultado.to_numpy()]) if len(ganhos) else (float("nan"),) * 2,
             "expectativa": {}, "expectativa_ic95": {}, "queda_maxima": {}}
    for payout in payouts:
        p = pnl_digital(operadas["direcao"].to_numpy(), operadas["retorno"].to_numpy(), payout)
        saida["expectativa"][payout] = float(p.mean()) if len(p) else float("nan")
        saida["expectativa_ic95"][payout] = intervalo_por_blocos(p, blocos) if len(p) else (float("nan"),) * 2
        acumulado = np.cumsum(p)
        saida["queda_maxima"][payout] = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], acumulado]))[1:] - acumulado)) if len(p) else 0.0
    return saida


def comparar(candidata: pd.DataFrame, referencia: pd.DataFrame, payout: float) -> dict:
    """Diferença pareada de resultado por oportunidade. Onde uma das duas não aposta, ela vale zero.

    As oportunidades são a união dos momentos das duas. O intervalo e o valor-p sorteiam blocos (dia × ativo).
    """
    chave = ["ativo", "tempo"]
    c = candidata.assign(pnl=pnl_digital(candidata["direcao"].to_numpy(), candidata["retorno"].to_numpy(), payout))[chave + ["pnl"]]
    r = referencia.assign(pnl=pnl_digital(referencia["direcao"].to_numpy(), referencia["retorno"].to_numpy(), payout))[chave + ["pnl"]]
    juntas = c.merge(r, on=chave, how="outer", suffixes=("_c", "_r")).fillna({"pnl_c": 0.0, "pnl_r": 0.0})
    d = (juntas["pnl_c"] - juntas["pnl_r"]).to_numpy()
    blocos = _blocos(juntas)
    baixo, alto = intervalo_por_blocos(d, blocos)
    # Valor-p unilateral (a candidata é melhor) pela média dos blocos, que respeita a correlação dentro de cada bloco.
    por_bloco = pd.Series(d).groupby(blocos).mean().to_numpy()
    erro = por_bloco.std(ddof=1) / np.sqrt(len(por_bloco)) if len(por_bloco) > 1 else float("nan")
    p = float(norm.sf(por_bloco.mean() / erro)) if erro and erro > 0 else (0.5 if por_bloco.mean() == 0 else float(por_bloco.mean() < 0))
    return {"oportunidades": int(len(d)), "blocos": int(len(por_bloco)), "diferenca": float(d.mean()), "ic95": (baixo, alto), "p_unilateral": p,
            "candidata": float(juntas["pnl_c"].mean()), "referencia": float(juntas["pnl_r"].mean())}
