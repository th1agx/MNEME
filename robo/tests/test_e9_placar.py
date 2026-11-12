"""G0: o placar compara qualquer política com a referência nas mesmas entradas, com a correlação entre apostas respeitada."""

import numpy as np
import pandas as pd
import pytest

from mneme.e9.placar import apostas, comparar, intervalo_por_blocos, placar

INICIO = pd.Timestamp("2026-01-01", tz="UTC")


def velas(retornos: np.ndarray) -> pd.DataFrame:
    f = 100 * np.exp(np.cumsum(retornos))
    a = np.concatenate([[100.0], f[:-1]])
    t = pd.date_range(INICIO, periods=len(f), freq="min")
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f), "minima": np.minimum(a, f), "fechamento": f, "volume": 1.0}, index=t)


def test_quem_sabe_o_futuro_acerta_tudo_e_quem_aposta_ao_contrario_erra_tudo():
    r = np.random.default_rng(0).normal(0, 1e-3, 3000)
    v = velas(r)
    tempos = v.index[100:2900:7]
    ret = v["fechamento"].shift(-3).reindex(tempos) / v["abertura"].shift(-2).reindex(tempos) - 1  # a convenção do motor
    certo = apostas("BTCUSDT", v, tempos, np.sign(ret.to_numpy()), expiracao=2)
    assert placar(certo)["acerto"] == 1.0
    assert placar(apostas("BTCUSDT", v, tempos, -np.sign(ret.to_numpy()), expiracao=2))["acerto"] == 0.0


def test_expectativa_por_payout_e_queda_maxima():
    a = pd.DataFrame({"ativo": "X", "tempo": pd.date_range(INICIO, periods=4, freq="D"), "direcao": 1, "retorno": [0.01, -0.01, -0.01, 0.01]})
    p = placar(a, payouts=(0.8,))
    assert p["acerto"] == 0.5 and p["expectativa"][0.8] == pytest.approx((0.8 - 1 - 1 + 0.8) / 4)
    assert p["queda_maxima"][0.8] == pytest.approx(2.0)


def test_empate_e_abstencao_nao_contam_no_acerto():
    a = pd.DataFrame({"ativo": "X", "tempo": pd.date_range(INICIO, periods=4, freq="D"), "direcao": [1, 1, 0, -1], "retorno": [0.01, 0.0, 0.02, -0.01]})
    p = placar(a, payouts=(0.85,))
    assert p["apostas"] == 3 and p["com_resultado"] == 2 and p["acerto"] == 1.0
    assert p["expectativa"][0.85] == pytest.approx((0.85 + 0 + 0.85) / 3)


def test_politicas_iguais_nao_tem_diferenca_e_melhor_aparece():
    r = np.random.default_rng(1).normal(0, 1e-3, 20000)
    v = velas(r)
    tempos = v.index[100:19900:5]
    ruido = np.random.default_rng(2).choice([-1, 1], len(tempos))
    ref = apostas("BTCUSDT", v, tempos, ruido, expiracao=1)
    igual = comparar(ref, ref, payout=0.85)
    assert igual["diferenca"] == 0 and igual["ic95"][0] <= 0 <= igual["ic95"][1]
    ret = ref["retorno"].to_numpy()
    sabe = np.where(np.random.default_rng(3).random(len(ret)) < 0.3, np.sign(ret), ruido)  # acerta 30% a mais das vezes
    melhor = comparar(apostas("BTCUSDT", v, tempos, sabe, expiracao=1), ref, payout=0.85)
    assert melhor["diferenca"] > 0 and melhor["ic95"][0] > 0 and melhor["p_unilateral"] < 0.01


def test_abster_vale_zero_na_comparacao_pareada():
    ref = pd.DataFrame({"ativo": "X", "tempo": pd.date_range(INICIO, periods=2, freq="D"), "direcao": [1, 1], "retorno": [0.01, -0.01]})
    so_a_boa = ref.assign(direcao=[1, 0])
    c = comparar(so_a_boa, ref, payout=0.85)
    assert c["diferenca"] == pytest.approx((0 - (-1)) / 2)  # deixou de perder 1 em 2 apostas


def test_intervalo_por_blocos_e_mais_largo_quando_os_resultados_andam_juntos():
    r = np.random.default_rng(4)
    dias = np.repeat(np.arange(40), 50)
    independente = r.normal(0, 1, len(dias))
    junto = np.repeat(r.normal(0, 1, 40), 50) + r.normal(0, 0.1, len(dias))
    largura = lambda x: np.diff(intervalo_por_blocos(x, dias))[0]
    assert largura(junto) > 3 * largura(independente)
