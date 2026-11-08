"""A versão vetorizada do perfil de volume dá exatamente o mesmo que o laço original, bit a bit."""

import numpy as np
import pandas as pd

from mneme.metodologias import _escala, perfil_de_volume


def laco(v: pd.DataFrame, atr: pd.Series, janela: int = 96, faixas: int = 24) -> pd.DataFrame:
    """O laço original, mantido aqui como referência."""
    tipico = ((v["maxima"] + v["minima"] + v["fechamento"]) / 3).to_numpy()
    volume, f = v["volume"].to_numpy(), v["fechamento"].to_numpy()
    poc, dentro = np.full(len(v), np.nan), np.full(len(v), np.nan)
    for t in range(janela - 1, len(v)):
        precos, pesos = tipico[t - janela + 1:t + 1], volume[t - janela + 1:t + 1]
        if np.isnan(precos).any() or pesos.sum() == 0:
            continue
        hist, bordas = np.histogram(precos, faixas, weights=pesos)
        meios = (bordas[:-1] + bordas[1:]) / 2
        topo = int(hist.argmax())
        poc[t] = meios[topo]
        ordem = np.argsort(hist)[::-1]
        escolhidas = ordem[:int(np.searchsorted(np.cumsum(hist[ordem]), 0.7 * hist.sum())) + 1]
        dentro[t] = float(meios[escolhidas].min() <= f[t] <= meios[escolhidas].max())
    return pd.DataFrame({"vp_dist_poc": (v["fechamento"] - poc) / _escala(atr), "vp_na_area_valor": dentro}, index=v.index)


def mercado(n: int, semente: int, casos_dificeis: bool) -> tuple[pd.DataFrame, pd.Series]:
    r = np.random.default_rng(semente)
    f = 100 + np.cumsum(r.normal(0, 0.3, n))
    if casos_dificeis:
        f = np.round(f, 1)  # preços repetidos: empates no histograma e nas bordas das faixas
        f[200:330] = f[200]  # janela inteira com o mesmo preço
    maxima, minima = f + np.abs(r.normal(0, 0.2, n)), f - np.abs(r.normal(0, 0.2, n))
    if casos_dificeis:
        maxima, minima = np.round(maxima, 1), np.round(minima, 1)
        maxima[200:330] = minima[200:330] = f[200:330]
    volume = r.exponential(5, n)
    if casos_dificeis:
        volume = np.round(volume)  # volumes iguais: empates na ordenação das faixas
        volume[500:620] = 0  # janela sem negócio
        f[min(700, n - 30)] = np.nan  # vela faltando
    idx = pd.date_range("2026-11-01", periods=n, freq="min", tz="UTC")
    v = pd.DataFrame({"abertura": f, "maxima": maxima, "minima": minima, "fechamento": f, "volume": volume}, index=idx)
    atr = pd.Series(r.uniform(0, 1, n), index=idx).where(lambda s: s > 0.05, 0.0)
    return v, atr


def test_igual_ao_laco_bit_a_bit():
    for semente in range(12):
        for dificil in (False, True):
            v, atr = mercado(1500, semente, dificil)
            pd.testing.assert_frame_equal(perfil_de_volume(v, atr), laco(v, atr), check_exact=True)


def test_igual_com_janela_e_faixas_diferentes_e_serie_curta():
    v, atr = mercado(400, 3, True)
    pd.testing.assert_frame_equal(perfil_de_volume(v, atr, janela=20, faixas=7), laco(v, atr, janela=20, faixas=7), check_exact=True)
    curto, atr_curto = v.iloc[:50], atr.iloc[:50]
    pd.testing.assert_frame_equal(perfil_de_volume(curto, atr_curto), laco(curto, atr_curto), check_exact=True)
