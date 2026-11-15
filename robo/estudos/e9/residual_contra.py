"""Exploratório (depois de ver o resultado): o motor contra "apostar contra a última vela" nas mesmas apostas."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.argv = sys.argv[:1]
from residual_motor import INICIO, FIM, PAYOUT, ultima_vela
from mneme.dados.armazem import ArmazemVelas
from mneme.e9.confirmacao import apostas_motor
from mneme.e9.placar import pnl_digital
from mneme.laboratorio.confluencia import grade_de_sinais
D = Path.home() / "mneme/robo/dados"; arm = ArmazemVelas(D / "mercado"); velas = {}; linhas = []
for e in Path("codigo/estrategias_operadas.txt").read_text().split():
    ativo, _, k, x = e.split("|"); k, x = int(k[:-1]), int(x[:-1])
    if ativo not in velas: velas[ativo] = arm.ler(ativo, inicio=INICIO.to_pydatetime(), fim=FIM.to_pydatetime())
    m = json.loads((D / "modelos/motor" / f"{e.replace(chr(124), chr(95))}.json").read_text())
    a = apostas_motor(velas[ativo], m, ativo, k, x, INICIO, FIM, grade_de_sinais(velas[ativo], k))
    ult = ultima_vela(velas[ativo], pd.DatetimeIndex(a["tempo"]))
    for nome, d in (("motor", a["direcao"].to_numpy()), ("contra_ultima", -ult), ("seguir_ultima", ult)):
        p = pnl_digital(d, a["retorno"].to_numpy(), PAYOUT); lado = np.sign(d) * np.sign(a["retorno"].to_numpy()); ok = (d != 0) & (lado != 0)
        meio = len(a) // 2
        linhas.append({"estrategia": e, "politica": nome, "apostas": int((d != 0).sum()), "acerto": float((lado[ok] > 0).mean()), "exp": float(p.mean()),
                       "exp_metade1": float(p[:meio].mean()), "exp_metade2": float(p[meio:].mean())})
    linhas.append({"estrategia": e, "politica": "concorda_contra", "apostas": int(len(a)), "acerto": float((a["direcao"].to_numpy() == -ult).mean()), "exp": np.nan, "exp_metade1": np.nan, "exp_metade2": np.nan})
t = pd.DataFrame(linhas); pd.set_option("display.width", 200); print(t.round(4).to_string(index=False))
g = t[t.politica != "concorda_contra"].groupby("politica").apply(lambda s: pd.Series({"apostas": s.apostas.sum(), "exp_ponderada": (s.exp * s.apostas).sum() / s.apostas.sum(), "m1": (s.exp_metade1 * s.apostas).sum() / s.apostas.sum(), "m2": (s.exp_metade2 * s.apostas).sum() / s.apostas.sum()}))
print(g.round(4))
