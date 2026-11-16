"""M2: fluxo no cripto (A) e prazos maiores nas moedas (B), walk-forward mensal no bloco de exploração.

Registro em estudos/e9/registro_m2.json. Desvio registrado: o modelo é o HistGradientBoostingClassifier do scikit-learn (mesma
família do LightGBM), porque o LightGBM não carrega no Mac sem instalar biblioteca do sistema e a VPS está em medição.

    python estudos/e9/rodar_m2.py <pasta velas_1m> <saida.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

FIM = "2026-02-01"
EMPATE = 1 / 1.85
COBERTURAS = (1.0, 0.2, 0.1, 0.05)
CRIPTO = ("ETHUSDT", "BTCUSDT", "SOLUSDT")
MOEDAS = {"EURUSD": -1, "GBPUSD": -1, "USDJPY": 1, "USDCAD": 1}
OURO = "XAUUSD"
PRAZOS_MOEDAS = (15, 30, 60)
SORTEIOS = 5000
MESES_MINIMOS = 4


def carregar(pasta: Path, par: str) -> pd.DataFrame:
    arqs = sorted(a for a in (pasta / par).glob("*.parquet") if a.stem < FIM)
    v = pd.concat([pd.read_parquet(a) for a in arqs]).drop_duplicates("abertura_em").set_index("abertura_em").sort_index()
    grade = pd.date_range(v.index[0], v.index[-1], freq="1min")
    return v.reindex(grade)


def atributos_preco(v: pd.DataFrame) -> pd.DataFrame:
    lc = np.log(v["fechamento"])
    r1 = lc.diff()
    x = pd.DataFrame({f"r{k}": lc.diff(k) for k in (1, 5, 15, 60)}, index=v.index)
    x["vol60"] = r1.rolling(60, min_periods=40).std()
    hi, lo = v["maxima"].rolling(60, min_periods=40).max(), v["minima"].rolling(60, min_periods=40).min()
    x["pos60"] = (v["fechamento"] - lo) / (hi - lo)
    x["hora"] = v.index.hour
    for k in ("r1", "r5", "r15", "r60"):
        x[k + "_z"] = x[k] / x["vol60"]
    return x


def atributos_fluxo(v: pd.DataFrame) -> pd.DataFrame:
    vol, comp, neg = v["volume"], v["volume_comprador"], v["negocios"]
    saldo = 2 * comp - vol
    x = pd.DataFrame(index=v.index)
    for k in (1, 5, 15):
        x[f"imb{k}"] = saldo.rolling(k).sum() / vol.rolling(k).sum()
    x["vol_rel"] = vol / vol.rolling(60, min_periods=40).mean()
    x["neg_rel"] = neg / neg.rolling(60, min_periods=40).mean()
    x["saldo15_60"] = saldo.rolling(15).sum() / vol.rolling(60, min_periods=40).sum()
    x["tam_medio_rel"] = (vol / neg) / (vol / neg).rolling(60, min_periods=40).mean()
    return x


def alvo(v: pd.DataFrame, prazo: int) -> pd.Series:
    mov = np.sign(v["fechamento"].shift(-prazo) - v["fechamento"])
    return mov.where(mov != 0)  # empate fora


def modelo():
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=500,
                                          l2_regularization=1.0, random_state=0)


def walk_forward(x: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    """Treina com todos os meses anteriores e testa no seguinte. Os limites de confiança vêm só do treino."""
    ok = y.notna() & x.notna().sum(axis=1).gt(len(x.columns) // 2)
    x, y = x[ok], y[ok]
    mes = x.index.to_period("M")
    meses = sorted(mes.unique())
    partes = []
    for i in range(MESES_MINIMOS, len(meses)):
        tr, te = mes < meses[i], mes == meses[i]
        xt, yt = x[tr], (y[tr] > 0).astype(int)
        if len(xt) > 400_000:  # treino recente basta e mantém o tempo controlado
            xt, yt = xt.iloc[-400_000:], yt.iloc[-400_000:]
        m = modelo().fit(xt, yt)
        conf_tr = np.abs(m.predict_proba(xt.iloc[::5])[:, 1] - 0.5)
        limites = {c: (np.quantile(conf_tr, 1 - c) if c < 1 else -1.0) for c in COBERTURAS}
        p = m.predict_proba(x[te])[:, 1]
        partes.append(pd.DataFrame({"acertou": (np.where(p >= 0.5, 1, -1) == y[te].to_numpy()).astype(float),
                                    "conf": np.abs(p - 0.5), **{f"lim_{c}": limites[c] for c in COBERTURAS}}, index=x[te].index))
    return pd.concat(partes) if partes else pd.DataFrame()


def placar(r: pd.DataFrame, cobertura: float, familia: int, semente: int = 7) -> dict:
    s = r[r["conf"] >= r[f"lim_{cobertura}"]]["acertou"]
    if s.empty:
        return {"apostas": 0}
    por = s.groupby(s.index.date).agg(["sum", "count"])
    idx = np.random.default_rng(semente).integers(0, len(por), (SORTEIOS, len(por)))
    b = por["sum"].to_numpy()[idx].sum(1) / por["count"].to_numpy()[idx].sum(1)
    baixo_fam = float(np.quantile(b, 0.05 / familia))
    return {"apostas": int(len(s)), "por_dia": float(len(s) / len(por)), "acerto": float(s.mean()),
            "limite_baixo_95": float(np.quantile(b, 0.05)), "limite_baixo_familia": baixo_fam, "passa": baixo_fam > EMPATE}


def main() -> None:
    pasta, destino = Path(sys.argv[1]), Path(sys.argv[2])
    saida: dict = {"registro": "estudos/e9/registro_m2.json", "A": {}, "B": {}}

    for par in CRIPTO:
        v = carregar(pasta, par)
        xp, xf, y = atributos_preco(v), atributos_fluxo(v), alvo(v, 5)
        rp, rpf = walk_forward(xp, y), walk_forward(pd.concat([xp, xf], axis=1), y)
        saida["A"][par] = {f"{c:.0%}": {"P": placar(rp, c, 12), "PF": placar(rpf, c, 12)} for c in COBERTURAS}
        print(par, json.dumps({k: (round(z["P"].get("acerto", 0), 4), round(z["PF"].get("acerto", 0), 4), round(z["PF"].get("limite_baixo_familia", 0), 4))
                               for k, z in saida["A"][par].items()}), flush=True)

    velas = {p: carregar(pasta, p) for p in (*MOEDAS, OURO)}
    grade = velas["EURUSD"].index
    for p in velas:
        grade = grade.union(velas[p].index)
    lado = pd.DataFrame({p: np.log(velas[p]["fechamento"].reindex(grade)) for p in MOEDAS})
    for par in (*MOEDAS, OURO):
        v = velas[par].reindex(grade)
        x = atributos_preco(v)
        outros = [q for q in MOEDAS if q != par]
        for k in (5, 15, 60):
            x[f"usd{k}"] = sum(lado[q].diff(k) * MOEDAS[q] for q in outros) / len(outros)
        x["dia_semana"] = x.index.dayofweek
        saida["B"][par] = {}
        for prazo in PRAZOS_MOEDAS:
            r = walk_forward(x, alvo(v, prazo))
            saida["B"][par][f"{prazo}min"] = {f"{c:.0%}": placar(r, c, 60) for c in COBERTURAS}
            print(par, prazo, json.dumps({k: (round(z.get("acerto", 0), 4), round(z.get("limite_baixo_familia", 0), 4)) for k, z in saida["B"][par][f"{prazo}min"].items()}), flush=True)

    destino.write_text(json.dumps(saida, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
