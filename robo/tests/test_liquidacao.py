"""Paridade: laboratório, estudos e motor liquidam a mesma operação do mesmo jeito (mneme.liquidacao)."""

import numpy as np
import pandas as pd
import pytest

from mneme.laboratorio.backtest import CustoSpot, apostas_direcao, operacoes_posicao
from mneme.laboratorio.horizontes import retorno_da_operacao, uma_por_vez
from mneme.liquidacao import liquidar_digital, liquidar_posicao, pnl_digital
from mneme.motor.modalidades import liquidar_fixa, liquidar_stop

UM = pd.Timedelta(minutes=1)


def velas(n=4000, semente=3, buracos=True):
    rng = np.random.default_rng(semente)
    retorno = rng.normal(0, 0.0015, n)
    retorno[rng.choice(n, 25, replace=False)] += rng.choice([-1, 1], 25) * 0.01  # saltos que abrem além do stop
    fechamento = 100 * np.exp(np.cumsum(retorno))
    abertura = np.r_[100.0, fechamento[:-1]] * np.exp(np.where(np.abs(retorno) > 0.008, np.sign(retorno) * 0.006, 0))
    maxima = np.maximum(abertura, fechamento) * (1 + rng.uniform(0, 0.001, n))
    minima = np.minimum(abertura, fechamento) * (1 - rng.uniform(0, 0.001, n))
    indice = pd.date_range("2026-03-02", periods=n, freq="1min", tz="UTC")
    v = pd.DataFrame({"abertura": abertura, "maxima": maxima, "minima": minima, "fechamento": np.round(fechamento, 2)}, index=indice)
    if buracos:
        v = v.drop(v.index[rng.choice(np.arange(10, n - 10), 40, replace=False)])
    return v


def sinais(v, semente=4, chance=0.03):
    rng = np.random.default_rng(semente)
    return pd.Series(np.where(rng.random(len(v)) < chance, rng.choice([-1, 1], len(v)), 0), index=v.index)


@pytest.mark.parametrize("minutos", [1, 5, 15])
def test_expiracao_fixa_laboratorio_e_motor_dao_o_mesmo_resultado(minutos):
    v, s = velas(), None
    s = sinais(v)
    apostas = apostas_direcao(v, s, minutos, 0.85)
    assert len(apostas) > 30
    for _, a in apostas.iterrows():
        m = liquidar_fixa(v, a["quando"] + UM, minutos, int(a["direcao"]), 0.85)
        assert m is not None and m["resultado"] == ("ganho" if a["ganhou"] else "perda")
        assert m["pnl"] == pytest.approx(a["retorno"])


def test_estudos_de_horizonte_aceitam_as_mesmas_operacoes_que_o_backtest():
    v = velas(buracos=False)
    s = sinais(v)
    for minutos in (5, 15):
        apostas = apostas_direcao(v, s, minutos, 0.85)
        tempos = pd.DatetimeIndex(s[s != 0].index)
        aceitos = uma_por_vez(tempos, 0, minutos)
        r = retorno_da_operacao(v, tempos[aceitos], 0, minutos) * s[tempos[aceitos]].to_numpy()
        validos = ~np.isnan(r) & (r != 0)
        assert list(tempos[aceitos][validos]) == list(apostas["quando"])
        assert list(r[validos] > 0) == list(apostas["ganhou"])


def test_stop_e_alvo_laboratorio_e_motor_saem_no_mesmo_preco_e_motivo():
    v = velas()
    s = sinais(v, chance=0.01)
    atr = (v["maxima"] - v["minima"]).rolling(14).mean() * 3
    ops = operacoes_posicao(v, s, atr, alvo_atr=2.0, stop_atr=1.0, velas_max=60, custo=CustoSpot(0.0, 0.0), so_compra=False)
    assert len(ops) > 15 and set(ops["saida"]) >= {"stop", "alvo"}
    for _, o in ops.iterrows():
        a = float(atr[o["quando"]])
        m = liquidar_stop(v, o["quando"] + UM, 60, int(o["lado"]), 1.0 * a, 2.0 * a, 0.0)
        assert m is not None and m["encerrado_por"] == o["saida"]
        assert o["lado"] * (m["preco_saida"] / m["preco_entrada"] - 1) == pytest.approx(o["retorno"])


def test_vela_que_abre_alem_do_stop_sai_na_abertura():
    a = np.array([100.0, 100.0, 95.0, 96.0])
    h = np.array([100.5, 100.5, 96.0, 97.0])
    l = np.array([99.5, 99.5, 94.0, 95.0])
    c = np.array([100.0, 100.0, 95.5, 96.5])
    p = liquidar_posicao(a, h, l, c, 1, 3, 1, 2.0, 4.0)
    assert (p.motivo, p.preco_saida, p.saida) == ("stop", 95.0, 2)  # e não 98,0, o preço do stop
    v = pd.DataFrame({"abertura": a, "maxima": h, "minima": l, "fechamento": c}, index=pd.date_range("2026-03-02", periods=4, freq="1min", tz="UTC"))
    m = liquidar_stop(v, v.index[1], 3, 1, 2.0, 4.0, 0.0)
    assert m["preco_saida"] == 95.0 and m["encerrado_por"] == "stop"


def test_sem_preco_ou_prazo_incompleto_nao_apura():
    a = np.array([100.0, np.nan, 101.0])
    f = np.array([100.0, np.nan, 101.0])
    assert liquidar_digital(a, f, 1, 1, 1) is None  # entrada sem preço
    assert liquidar_digital(a, f, 2, 2, 1) is None  # prazo além das velas
    assert liquidar_posicao(a, a, a, f, 0, 5, 1, 5.0, 5.0) is None  # nenhuma barreira e o prazo ainda não terminou
    assert liquidar_posicao(a, a, a, f, 0, 5, 1, 5.0, 0.5).motivo == "alvo"  # barreira tocada antes do fim: já apura


def test_empate_depende_da_regra_da_plataforma():
    assert pnl_digital("empate", 0.85) == 0.0
    assert pnl_digital("empate", 0.85, empate="perde") == -1.0
    assert pnl_digital("ganho", 0.85) == 0.85 and pnl_digital("perda", 0.85) == -1.0
