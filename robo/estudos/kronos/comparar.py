"""Estudo isolado: Kronos (zero-shot) contra o LightGBM e o XGBoost do MNEME, nos mesmos pontos, períodos e ativos.

Roda só no ambiente de laboratório (~/lab/kronos na A1), com prioridade baixa. Não toca nos serviços nem na área selada.

    python comparar.py base      # atributos, previsões fora da amostra do LightGBM e do XGBoost, e o sorteio dos pontos
    python comparar.py kronos --modelo mini [--limite 250]   # trajetórias do Kronos para os pontos, com retomada
    python comparar.py analise   # métricas e comparação

Pré-treino do Kronos até junho de 2024 (artigo, seção de avaliação); os dados do MNEME começam em 01/11/2024.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROBO = Path(os.getenv("MNEME_ROBO", "/home/ubuntu/mneme/robo"))
KRONOS_SRC = Path(os.getenv("KRONOS_SRC", "/home/ubuntu/lab/kronos/kronos_src"))
SAIDA = Path(os.getenv("KRONOS_SAIDA", "/home/ubuntu/lab/kronos/resultados"))
sys.path.insert(0, str(ROBO))

from mneme.laboratorio.validacao import dobras_walk_forward  # noqa: E402

PARES = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HORIZONTES = {15: ("5min", 3), 60: ("15min", 4)}  # horizonte: (vela de entrada do Kronos, velas previstas)
PONTOS = 800
CONTEXTO = 256
TRAJETORIAS = 8
SEMENTE = 0
REVISOES = {"mini": ("NeoQuasar/Kronos-mini", "f4e68697d9", "NeoQuasar/Kronos-Tokenizer-2k", "26966d0035"),
            "small": ("NeoQuasar/Kronos-small", "901c26c133", "NeoQuasar/Kronos-Tokenizer-base", "0e0117387f")}


# ---------- 1. base: o que o MNEME já faz, nos mesmos cortes de sempre ----------

def base() -> None:
    from mneme.dados.armazem import ArmazemVelas
    from mneme.laboratorio.__main__ import SELADO_DESDE, _base_de_previsao
    from mneme.laboratorio.avaliacao import regimes, separar_selado
    from mneme.laboratorio.dataset import alvos, amostrar
    from mneme.laboratorio.previsao import _lgb_c, _xgb_c, fora_da_amostra
    import lightgbm as lgb

    raiz = str(ROBO / "dados" / "mercado")
    armazem = ArmazemVelas(raiz)
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = []
    for par in PARES:
        atributos, v, _ = _base_de_previsao(armazem, par, raiz)
        for h in HORIZONTES:
            x, y = amostrar(atributos, alvos(v, h), h)
            dev, _ = separar_selado(x.index, SELADO_DESDE)
            x, y = x[dev], y[dev]
            dobras = dobras_walk_forward(len(x), 5, 1, 2)
            p_lgb = fora_da_amostra(_lgb_c, x, y["sobe"], dobras)
            p_xgb = fora_da_amostra(_xgb_c, x, y["sobe"], dobras)
            assert (p_lgb.posicoes == p_xgb.posicoes).all()
            # Volatilidade futura, como no estudo atual: LightGBM de regressão fora da amostra e a referência ajustada no treino.
            vol = np.full(len(x), np.nan)
            ref = np.log(x["v_volatilidade_60"].replace(0, np.nan))
            for d in dobras:
                ok = y["vol_futura"].iloc[d.treino].notna()
                m = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.7, subsample_freq=1,
                                      colsample_bytree=0.7, random_state=0, n_jobs=2, verbose=-1).fit(x.iloc[d.treino][ok.to_numpy()], y["vol_futura"].iloc[d.treino][ok])
                vol[d.teste] = m.predict(x.iloc[d.teste])
            bloco = np.concatenate([np.full(n, i) for i, n in enumerate(p_lgb.blocos)])
            fora = pd.DataFrame({"pos": p_lgb.posicoes, "lgb": p_lgb.prob, "xgb": p_xgb.prob, "bloco": bloco})
            rng = np.random.default_rng(SEMENTE)
            escolhidos = np.sort(rng.choice(len(fora), size=min(PONTOS, len(fora)), replace=False))
            sub = fora.iloc[escolhidos]
            idx = x.index[sub["pos"].to_numpy()]
            reg = regimes(x.loc[idx])
            for (_, f), t, r in zip(sub.iterrows(), idx, reg):
                linhas.append({"par": par, "h": h, "t": t.isoformat(), "bloco": int(f["bloco"]), "lgb": float(f["lgb"]), "xgb": float(f["xgb"]),
                               "lgb_vol": float(vol[int(f["pos"])]), "ref_vol": float(ref.iloc[int(f["pos"])]), "regime": r,
                               "sobe": float(y["sobe"].loc[t]), "retorno": float(y["retorno"].loc[t]), "vol_futura": float(y["vol_futura"].loc[t])})
            print(json.dumps({"par": par, "h": h, "linhas_dev": len(x), "fora_da_amostra": len(fora), "pontos": len(sub),
                              "de": str(x.index[0]), "ate": str(x.index[-1])}), flush=True)
    pd.DataFrame(linhas).to_parquet(SAIDA / "pontos.parquet")


# ---------- 2. Kronos: trajetórias separadas, só com velas já fechadas ----------

def _velas(par: str, tempo: str) -> pd.DataFrame:
    from mneme import indicadores as ind
    from mneme.dados.armazem import ArmazemVelas
    v = ArmazemVelas(str(ROBO / "dados" / "mercado")).ler(par)
    m = ind.reamostrar(v.dropna(subset=["fechamento"]), tempo).dropna()
    return m.rename(columns={"abertura": "open", "maxima": "high", "minima": "low", "fechamento": "close"})[["open", "high", "low", "close", "volume"]]


def kronos(modelo: str, limite: int | None, lote: int = 2) -> None:
    import torch
    sys.path.insert(0, str(KRONOS_SRC))
    from model import Kronos, KronosPredictor, KronosTokenizer
    torch.set_num_threads(int(os.getenv("KRONOS_THREADS", "2")))
    nome, rev, tok, rev_tok = REVISOES[modelo]
    preditor = KronosPredictor(Kronos.from_pretrained(nome, revision=rev), KronosTokenizer.from_pretrained(tok, revision=rev_tok), device="cpu", max_context=512)
    pontos = pd.read_parquet(SAIDA / "pontos.parquet")
    if limite:
        pontos = pontos.groupby(["par", "h"], group_keys=False).apply(lambda g: g.iloc[np.linspace(0, len(g) - 1, min(limite, len(g))).astype(int)])
    arquivo = SAIDA / f"kronos_{modelo}.jsonl"
    feitos = {(l["par"], l["h"], l["t"]) for l in map(json.loads, arquivo.read_text().splitlines())} if arquivo.exists() else set()
    for (par, h), grupo in pontos.groupby(["par", "h"]):
        tempo, passos = HORIZONTES[h]
        velas = _velas(par, tempo)
        duracao = pd.Timedelta(tempo)
        pendentes = [r for r in grupo.itertuples() if (par, h, r.t) not in feitos]
        for i in range(0, len(pendentes), lote):
            parte, dfs, xs, ys, chaves = pendentes[i:i + lote], [], [], [], []
            for r in parte:
                agora = pd.Timestamp(r.t) + pd.Timedelta(minutes=1)  # fim da vela de 1 minuto da decisão
                fechadas = velas[velas.index + duracao <= agora].iloc[-CONTEXTO:]
                if len(fechadas) < CONTEXTO:
                    continue
                futuro = pd.Series(pd.date_range(fechadas.index[-1] + duracao, periods=passos, freq=tempo))
                for _ in range(TRAJETORIAS):  # cópias com sample_count=1: cada uma é uma trajetória, sem a média interna
                    dfs.append(fechadas.reset_index(drop=True)); xs.append(pd.Series(fechadas.index)); ys.append(futuro)
                chaves.append((r, float(fechadas["close"].iloc[-1])))
            if not chaves:
                continue
            torch.manual_seed(SEMENTE + i); np.random.seed(SEMENTE + i)
            inicio = time.time()
            with torch.no_grad():
                saidas = preditor.predict_batch(dfs, xs, ys, pred_len=passos, T=1.0, top_p=0.9, sample_count=1, verbose=False)
            gasto = (time.time() - inicio) / len(chaves)
            with arquivo.open("a") as f:
                for j, (r, ultimo) in enumerate(chaves):
                    trajs = saidas[j * TRAJETORIAS:(j + 1) * TRAJETORIAS]
                    finais = np.array([s["close"].iloc[-1] / ultimo - 1 for s in trajs])
                    passos_log = np.array([np.diff(np.log(np.r_[ultimo, s["close"].to_numpy()])) for s in trajs])
                    faixa = np.array([(s["high"].max() - s["low"].min()) / ultimo for s in trajs])
                    f.write(json.dumps({"par": par, "h": h, "t": r.t, "k_prob": float((finais > 0).mean()), "k_ret": float(finais.mean()),
                                        "k_disp": float(finais.std()), "k_vol": float(np.log(passos_log.std() + 1e-9)), "k_faixa": float(faixa.mean()),
                                        "k_min": float(finais.min()), "k_max": float(finais.max()), "segundos": gasto}) + "\n")
            print(f"{modelo} {par} {h}: {min(i + lote, len(pendentes))}/{len(pendentes)} · {gasto:.1f}s por ponto", flush=True)


# ---------- 3. análise ----------

def _auc(real, prob):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(real, prob)) if len(np.unique(real)) > 1 else float("nan")


def _empilhar(d: pd.DataFrame, colunas: list[str]) -> np.ndarray:
    """Segundo estágio em walk-forward dentro da amostra: logística sobre as colunas dadas. NaN onde não há passado suficiente."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    prob = np.full(len(d), np.nan)
    for dobra in dobras_walk_forward(len(d), 5, 1, 2):
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, C=0.5)).fit(d[colunas].iloc[dobra.treino], d["sobe"].iloc[dobra.treino])
        prob[dobra.teste] = m.predict_proba(d[colunas].iloc[dobra.teste])[:, 1]
    return prob


def _r2_calibrado(d: pd.DataFrame, coluna: str) -> float:
    """Ajuste linear no passado (walk-forward) e R² no futuro, para não premiar ou punir a escala."""
    from sklearn.linear_model import LinearRegression
    prev = np.full(len(d), np.nan)
    ok = d[[coluna, "vol_futura"]].notna().all(axis=1).to_numpy()
    dd = d[ok]
    for dobra in dobras_walk_forward(len(dd), 5, 1, 2):
        m = LinearRegression().fit(dd[[coluna]].iloc[dobra.treino], dd["vol_futura"].iloc[dobra.treino])
        prev[np.flatnonzero(ok)[dobra.teste]] = m.predict(dd[[coluna]].iloc[dobra.teste])
    v = ~np.isnan(prev)
    r = d["vol_futura"].to_numpy()[v]
    return float(1 - np.mean((prev[v] - r) ** 2) / np.var(r))


def _bootstrap_diferenca(real, a, b, vezes=1000, bloco=20) -> tuple[float, float, float]:
    """Diferença de AUC (a − b) com bootstrap em blocos de pontos vizinhos no tempo. Devolve (diferença, IC 2,5%, IC 97,5%)."""
    rng = np.random.default_rng(SEMENTE)
    n = len(real)
    inicios = np.arange(0, n, bloco)
    difs = []
    for _ in range(vezes):
        escolha = np.concatenate([np.arange(s, min(s + bloco, n)) for s in rng.choice(inicios, size=len(inicios))])
        difs.append(_auc(real[escolha], a[escolha]) - _auc(real[escolha], b[escolha]))
    return _auc(real, a) - _auc(real, b), float(np.nanpercentile(difs, 2.5)), float(np.nanpercentile(difs, 97.5))


def analise(modelo: str) -> None:
    from scipy.stats import spearmanr
    pontos = pd.read_parquet(SAIDA / "pontos.parquet")
    k = pd.DataFrame(map(json.loads, (SAIDA / f"kronos_{modelo}.jsonl").read_text().splitlines())).drop_duplicates(["par", "h", "t"])
    d = pontos.merge(k, on=["par", "h", "t"]).sort_values(["par", "h", "t"]).reset_index(drop=True)
    saida = {"modelo": modelo, "pontos": len(d), "segundos_por_ponto": float(d["segundos"].median()), "por_grupo": []}
    for (par, h), g in d.groupby(["par", "h"]):
        g = g.dropna(subset=["sobe"]).reset_index(drop=True)
        real = g["sobe"].to_numpy()
        g["stack_lgb"] = _empilhar(g, ["lgb"])
        g["stack_lgb_k"] = _empilhar(g, ["lgb", "k_prob", "k_ret", "k_disp"])
        g["stack_xgb"] = _empilhar(g, ["xgb"])
        g["stack_xgb_k"] = _empilhar(g, ["xgb", "k_prob", "k_ret", "k_disp"])
        v = g["stack_lgb"].notna().to_numpy()
        linha = {"par": par, "h": h, "pontos": len(g),
                 "auc": {c: _auc(real, g[c].to_numpy()) for c in ("lgb", "xgb", "k_prob")},
                 "acerto": {c: float(((g[c] >= 0.5) == real).mean()) for c in ("lgb", "xgb", "k_prob")},
                 "auc_empilhado": {c: _auc(real[v], g[c].to_numpy()[v]) for c in ("stack_lgb", "stack_lgb_k", "stack_xgb", "stack_xgb_k")},
                 "ganho_kronos_sobre_lgb": _bootstrap_diferenca(real[v], g["stack_lgb_k"].to_numpy()[v], g["stack_lgb"].to_numpy()[v]),
                 "ganho_kronos_sobre_xgb": _bootstrap_diferenca(real[v], g["stack_xgb_k"].to_numpy()[v], g["stack_xgb"].to_numpy()[v]),
                 "ic_retorno": {"kronos": float(spearmanr(g["k_ret"], g["retorno"]).statistic), "lgb": float(spearmanr(g["lgb"], g["retorno"]).statistic)},
                 "r2_vol": {"kronos": _r2_calibrado(g, "k_vol"), "kronos_faixa": _r2_calibrado(g.assign(lf=np.log(g["k_faixa"] + 1e-9)), "lf"),
                            "lgb": _r2_calibrado(g, "lgb_vol"), "referencia": _r2_calibrado(g, "ref_vol")},
                 "cobertura_8_trajetorias": float(((g["retorno"] >= g["k_min"]) & (g["retorno"] <= g["k_max"])).mean()),
                 "auc_por_regime": {r: {"pontos": len(gr), "lgb": _auc(gr["sobe"].to_numpy(), gr["lgb"].to_numpy()), "kronos": _auc(gr["sobe"].to_numpy(), gr["k_prob"].to_numpy())}
                                    for r, gr in g.groupby("regime") if len(gr) >= 60}}
        saida["por_grupo"].append(linha)
        print(json.dumps(linha, ensure_ascii=False, default=float), flush=True)
    todos = d.dropna(subset=["sobe"])
    saida["geral"] = {"auc_lgb": _auc(todos["sobe"].to_numpy(), todos["lgb"].to_numpy()), "auc_xgb": _auc(todos["sobe"].to_numpy(), todos["xgb"].to_numpy()),
                      "auc_kronos": _auc(todos["sobe"].to_numpy(), todos["k_prob"].to_numpy()), "cobertura_nominal": (TRAJETORIAS - 1) / (TRAJETORIAS + 1)}
    (SAIDA / f"analise_{modelo}.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1, default=float))
    print(json.dumps(saida["geral"], default=float))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("etapa", choices=["base", "kronos", "analise"])
    p.add_argument("--modelo", default="mini", choices=list(REVISOES))
    p.add_argument("--limite", type=int)
    a = p.parse_args()
    if a.etapa == "base":
        base()
    elif a.etapa == "kronos":
        kronos(a.modelo, a.limite)
    else:
        analise(a.modelo)
