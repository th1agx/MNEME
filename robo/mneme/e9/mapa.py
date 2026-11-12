"""G0: mapa de previsibilidade. Onde existe sinal, por alvo, horizonte e ativo, antes de investir em qualquer ideia.

Protocolo fixado antes de rodar (PROTOCOLO, abaixo, e a nota do Vault "E9 - mapa de previsibilidade"). Usa só o período de
desenvolvimento: a validação (a partir de 2025-06) e a área selada (a partir de 2026-08) ficam intocadas.

Para cada célula (ativo, horizonte, alvo), um LightGBM pequeno com todos os atributos de vela do laboratório, em walk-forward
com embargo, mede o teto de previsibilidade fora da amostra:
- direção: AUC de "sobe" e o acerto dos 20% mais confiantes contra o empate;
- volatilidade: ganho de R² sobre a referência ingênua (a volatilidade recente persiste);
- extremo: AUC de um movimento maior que 2 desvios esperados para o horizonte.
Os intervalos sorteiam dias inteiros.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ..laboratorio.dataset import alvos, amostrar, construir
from ..laboratorio.validacao import dobras_walk_forward
from .regua import empate

PROTOCOLO = {
    "versao": "mapa_v1",
    "ativos": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "horizontes": [1, 5, 15, 60, 240],
    "alvos": ["direcao", "volatilidade", "extremo"],
    "inicio": "2024-11-01",
    "fim_desenvolvimento": "2025-06-01",
    "atributos": "laboratorio.dataset.construir (velas de 1 min; sem funding nem fluxo, que não têm histórico)",
    "modelo": "LightGBM(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=300, subsample=0.8, colsample=0.8)",
    "validacao": "walk-forward, 5 dobras, embargo de 2 pontos",
    "intervalo": "bootstrap de 300 sorteios de dias inteiros",
    "sinal_existe_se": "limite inferior do IC acima de 0,5 (AUC) ou acima de 0 (ganho de R²), depois de Holm na família de 45 células",
    "relevante_para_expiracao_fixa_se": "acerto dos 20% mais confiantes acima do empate de 54,05% com o IC",
}

SORTEIOS = 300


def _modelo(regressao: bool):
    parametros = dict(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=300, subsample=0.8, subsample_freq=1,
                      colsample_bytree=0.8, random_state=0, n_jobs=2, verbose=-1)
    return lgb.LGBMRegressor(**parametros) if regressao else lgb.LGBMClassifier(**parametros)


def preparar(v: pd.DataFrame, horizonte: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Atributos e alvos numa grade sem sobreposição. Inclui o alvo de extremo e a referência ingênua de volatilidade."""
    x = construir(v)
    y = alvos(v, horizonte)
    passos = np.log(v["fechamento"]).diff()
    esperado = passos.rolling(max(60, horizonte)).std() * np.sqrt(horizonte)
    y["extremo"] = (y["retorno"].abs() > 2 * esperado.reindex(y.index)).astype(float).where(y["retorno"].notna() & esperado.notna())
    y["vol_ingenua"] = np.log(passos.rolling(max(horizonte, 2)).std().replace(0, np.nan)).reindex(y.index)
    x, y = amostrar(x, y, horizonte)
    return x, y


def _dias(indice: pd.DatetimeIndex) -> np.ndarray:
    return pd.DatetimeIndex(indice).floor("D").asi8


def _bootstrap(metrica, dias: np.ndarray, semente: int = 0) -> tuple[float, float]:
    unicos = np.unique(dias)
    grupos = {d: np.flatnonzero(dias == d) for d in unicos}
    r = np.random.default_rng(semente)
    valores = []
    for _ in range(SORTEIOS):
        idx = np.concatenate([grupos[d] for d in r.choice(unicos, len(unicos))])
        valor = metrica(idx)
        if np.isfinite(valor):
            valores.append(valor)
    return float(np.quantile(valores, 0.025)), float(np.quantile(valores, 0.975))


def medir_celula(x: pd.DataFrame, y: pd.DataFrame, alvo: str, horizonte: int, payout: float = 0.85) -> dict | None:
    """None quando a célula não existe: a volatilidade em 1 min seria o desvio de um retorno só (desvio do protocolo registrado no Vault)."""
    if alvo == "volatilidade" and horizonte < 2:
        return None
    coluna = {"direcao": "sobe", "volatilidade": "vol_futura", "extremo": "extremo"}[alvo]
    validos = y[coluna].notna() & (y["vol_ingenua"].notna() if alvo == "volatilidade" else True)
    xv, yv = x[validos], y.loc[validos, coluna]
    dobras = dobras_walk_forward(len(xv), 5, 1, 2)
    previsto, real, posicoes = [], [], []
    for d in dobras:
        m = _modelo(alvo == "volatilidade").fit(xv.iloc[d.treino], yv.iloc[d.treino])
        p = m.predict(xv.iloc[d.teste]) if alvo == "volatilidade" else m.predict_proba(xv.iloc[d.teste])[:, 1]
        previsto.append(p)
        real.append(yv.iloc[d.teste].to_numpy())
        posicoes.append(d.teste)
    p, r, pos = np.concatenate(previsto), np.concatenate(real), np.concatenate(posicoes)
    dias = _dias(xv.index[pos])
    saida = {"alvo": alvo, "horizonte": horizonte, "amostras_teste": int(len(p)), "dias_teste": int(len(np.unique(dias)))}
    if alvo == "volatilidade":
        ingenua = y.loc[validos, "vol_ingenua"].to_numpy()[pos]
        # A referência ingênua é recalibrada só com o passado (a mesma escala do alvo): regressão linear nas dobras de treino.
        ajustada = np.empty_like(ingenua)
        inicio = 0
        for d, tamanho in zip(dobras, [len(q) for q in previsto]):
            a, b = np.polyfit(y.loc[validos, "vol_ingenua"].to_numpy()[d.treino], yv.to_numpy()[d.treino], 1)
            ajustada[inicio:inicio + tamanho] = a * ingenua[inicio:inicio + tamanho] + b
            inicio += tamanho

        def ganho(idx):
            sse_m, sse_i, sst = ((r[idx] - p[idx]) ** 2).sum(), ((r[idx] - ajustada[idx]) ** 2).sum(), ((r[idx] - r[idx].mean()) ** 2).sum()
            return (sse_i - sse_m) / sst if sst > 0 else np.nan

        tudo = np.arange(len(p))
        saida |= {"ganho_r2": float(ganho(tudo)), "ic95": _bootstrap(ganho, dias),
                  "r2_modelo": float(1 - ((r - p) ** 2).sum() / ((r - r.mean()) ** 2).sum())}
        return saida

    def auc(idx):
        return roc_auc_score(r[idx], p[idx]) if len(np.unique(r[idx])) == 2 else np.nan

    saida |= {"auc": float(auc(np.arange(len(p)))), "ic95": _bootstrap(auc, dias), "taxa_base": float(r.mean())}
    if alvo == "direcao":
        # Os 20% mais confiantes, com o limiar aprendido só no passado (quantil das previsões da dobra anterior).
        confianca = np.abs(p - 0.5)
        escolhidos = np.zeros(len(p), dtype=bool)
        inicio, limiar = 0, None
        for q in previsto:
            fim = inicio + len(q)
            if limiar is not None:
                escolhidos[inicio:fim] = confianca[inicio:fim] >= limiar
            limiar = np.quantile(confianca[inicio:fim], 0.8)
            inicio = fim
        acerto = ((p >= 0.5) == (r == 1)).astype(float)
        sel = np.flatnonzero(escolhidos)
        acerto_sel = acerto[sel]
        saida |= {"acerto_top20": float(acerto_sel.mean()) if len(sel) else np.nan,
                  "acerto_top20_ic95": _bootstrap(lambda idx: acerto_sel[idx].mean(), dias[sel]) if len(sel) else (np.nan, np.nan),
                  "empate": empate(payout), "apostas_top20": int(len(sel))}
    return saida
