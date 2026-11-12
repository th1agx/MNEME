"""G0: o mapa de previsibilidade acha sinal onde ele existe e não inventa onde não existe."""

import numpy as np
import pandas as pd

from mneme.e9.mapa import PROTOCOLO, medir_celula, preparar


def mercado(n=60_000, semente=0, direcao_plantada=0.0) -> pd.DataFrame:
    """Volatilidade que se agrupa (previsível) e, se pedido, uma pitada de direção previsível a partir do retorno anterior."""
    r = np.random.default_rng(semente)
    vol = np.exp(np.convolve(r.normal(0, 0.35, n), np.ones(240) / 240, mode="same") * 8 - 7)
    ret = np.zeros(n)
    choque = r.normal(0, 1, n)
    for i in range(1, n):
        ret[i] = vol[i] * choque[i] + direcao_plantada * ret[i - 1]
    f = 100 * np.exp(np.cumsum(ret))
    a = np.concatenate([[100.0], f[:-1]])
    t = pd.date_range("2024-11-01", periods=n, freq="min", tz="UTC")
    volume = r.lognormal(3, 0.5, n)
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) * (1 + vol / 4), "minima": np.minimum(a, f) * (1 - vol / 4), "fechamento": f,
                         "volume": volume, "volume_cotacao": volume * f, "volume_comprador": volume * r.uniform(0.3, 0.7, n), "negocios": 50}, index=t)


def test_protocolo_esta_fixado_e_fora_da_validacao():
    assert PROTOCOLO["fim_desenvolvimento"] == "2025-06-01" and set(PROTOCOLO["alvos"]) == {"direcao", "volatilidade", "extremo"}
    assert PROTOCOLO["horizontes"] == [1, 5, 15, 60, 240]


def test_volatilidade_agrupada_aparece_e_direcao_aleatoria_nao():
    x, y = preparar(mercado(), 5)
    vol = medir_celula(x, y, "volatilidade", 5)
    assert vol["ganho_r2"] > 0 and vol["ic95"][0] > 0
    direcao = medir_celula(x, y, "direcao", 5)
    assert direcao["ic95"][0] <= 0.5 <= direcao["ic95"][1]


def test_direcao_plantada_e_achada():
    x, y = preparar(mercado(direcao_plantada=0.25, semente=1), 1)
    d = medir_celula(x, y, "direcao", 1)
    assert d["auc"] > 0.55 and d["ic95"][0] > 0.5


def test_alvo_embaralhado_nao_tem_sinal():
    x, y = preparar(mercado(semente=2), 5)
    y = y.copy()
    y["sobe"] = np.random.default_rng(9).permutation(y["sobe"].to_numpy())
    d = medir_celula(x, y, "direcao", 5)
    assert abs(d["auc"] - 0.5) < 0.02


def test_intervalos_contem_a_estimativa():
    x, y = preparar(mercado(direcao_plantada=0.25, semente=1), 1)
    d = medir_celula(x, y, "direcao", 1)
    assert d["ic95"][0] <= d["auc"] <= d["ic95"][1]
    assert d["acerto_top20_ic95"][0] <= d["acerto_top20"] <= d["acerto_top20_ic95"][1]


def test_volatilidade_em_1_minuto_nao_existe_e_e_pulada():
    x, y = preparar(mercado(n=20_000), 1)
    assert medir_celula(x, y, "volatilidade", 1) is None
