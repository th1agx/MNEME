"""Conciliação: o preço que a plataforma mostrou contra a referência do MNEME no mesmo instante.

É daqui que sai o quanto o simulador pode confiar na referência para cada plataforma e ativo. A referência é de 1 minuto:
o preço num segundo do minuto é interpolado entre a abertura e o fechamento da vela (aproximação declarada). Ativos OTC
não têm referência externa: a cotação é da própria plataforma.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .plataformas import REFERENCIA


def _preco(v: pd.DataFrame, t: datetime) -> tuple[float | None, tuple[float, float] | None]:
    minuto = pd.Timestamp(t).floor("min")
    if minuto not in v.index:
        return None, None
    vela = v.loc[minuto]
    fracao = (pd.Timestamp(t) - minuto).total_seconds() / 60
    return float(vela["abertura"] + (vela["fechamento"] - vela["abertura"]) * fracao), (float(vela["minima"]), float(vela["maxima"]))


def conciliar(con: sqlite3.Connection, ler_velas, agora: datetime | None = None) -> dict:
    """Concilia as operações ainda não conciliadas. `ler_velas(serie, inicio, fim)` lê o armazém de velas."""
    agora = agora or datetime.now(timezone.utc)
    feitas, sem_referencia, sem_vela = 0, 0, 0
    pendentes = con.execute("SELECT o.* FROM operacoes_demo o LEFT JOIN conciliacao c ON c.id = o.id WHERE c.id IS NULL").fetchall()
    for o in pendentes:
        serie = None if o["otc"] else REFERENCIA.get(o["ativo"])
        if serie is None:
            sem_referencia += 1
            continue
        t0 = datetime.fromisoformat(o["aberta_em"])
        t1 = t0 + timedelta(minutes=o["expiracao_min"])
        v = ler_velas(serie, t0 - timedelta(minutes=2), t1 + timedelta(minutes=2))
        entrada, faixa = _preco(v, t0) if not v.empty else (None, None)
        saida, _ = _preco(v, t1) if not v.empty else (None, None)
        if entrada is None or saida is None:
            sem_vela += 1
            continue
        movimento = (saida - entrada) * o["direcao"]
        resultado_ref = "ganho" if movimento > 0 else "perda" if movimento < 0 else "empate"
        con.execute("INSERT OR REPLACE INTO conciliacao VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (o["id"], serie, entrada, saida, (o["preco_entrada"] / entrada - 1) * 1e4, (o["preco_saida"] / saida - 1) * 1e4,
                     int(faixa[0] * 0.9999 <= o["preco_entrada"] <= faixa[1] * 1.0001), resultado_ref,
                     int(resultado_ref == o["resultado"]), agora.isoformat()))
        feitas += 1
    con.commit()
    return {"conciliadas_agora": feitas, "sem_referencia_otc_ou_ativo": sem_referencia, "sem_vela_de_referencia": sem_vela}


def resumo(con: sqlite3.Connection) -> dict:
    saida = {}
    for (plat,) in con.execute("SELECT DISTINCT plataforma FROM operacoes_demo"):
        linhas = con.execute("SELECT c.*, o.ativo FROM conciliacao c JOIN operacoes_demo o ON o.id = c.id WHERE o.plataforma = ?", (plat,)).fetchall()
        if not linhas:
            saida[plat] = {"conciliadas": 0}
            continue
        div = np.abs([l["divergencia_entrada_bps"] for l in linhas])
        saida[plat] = {"conciliadas": len(linhas), "divergencia_entrada_bps_mediana": float(np.median(div)), "divergencia_entrada_bps_p90": float(np.quantile(div, 0.9)),
                       "entrada_dentro_da_vela": float(np.mean([l["entrada_dentro_da_vela"] for l in linhas])),
                       "resultado_concorda_com_referencia": float(np.mean([l["concorda"] for l in linhas]))}
    return saida
