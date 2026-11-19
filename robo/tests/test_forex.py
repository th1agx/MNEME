import numpy as np
import pandas as pd
import pytest

from mneme.laboratorio.forex import RegraSaida, conferir_cotacoes, disponiveis_para_treino, medir, simular, uma_carteira


def cotacoes(n=8):
    idx = pd.date_range("2026-07-01", periods=n, freq="1min", tz="UTC")
    bid = pd.DataFrame({"abertura": 1., "maxima": 1.0001, "minima": .9999, "fechamento": 1.}, index=idx)
    return bid, bid + .0002


@pytest.mark.parametrize("lado", [1, -1])
def test_mercado_parado_perde_spread_dos_dois_lados(lado):
    b, a = cotacoes()
    s = pd.Series([lado] + [0] * 7, index=b.index)
    r = simular(b, a, s, pd.Series(.001, index=b.index), RegraSaida(minutos=2))
    assert r.iloc[0]["entrada_em"] == b.index[1]
    assert r.iloc[0]["saida_em"] == b.index[3]
    assert r.iloc[0]["pips_bidask"] == pytest.approx(-2)
    m = medir(r, custo_extra_pips=.5)
    assert m["saldo_usd"] == pytest.approx(-.25)


def test_stop_precede_alvo_quando_a_vela_nao_revela_a_ordem():
    b, a = cotacoes()
    b.loc[b.index[1], ["maxima", "minima"]] = [1.003, .997]
    r = simular(b, a, pd.Series([1] + [0] * 7, index=b.index), pd.Series(.001, index=b.index), RegraSaida(1, 1, 3))
    assert r.iloc[0]["motivo"] == "stop"
    assert r.iloc[0]["preco_saida"] == pytest.approx(.9992)


def test_gap_contra_stop_executa_no_preco_disponivel():
    b, a = cotacoes()
    b.loc[b.index[2], ["abertura", "maxima", "minima", "fechamento"]] = [.998, .9981, .9979, .998]
    r = simular(b, a, pd.Series([1] + [0] * 7, index=b.index), pd.Series(.001, index=b.index), RegraSaida(1, 3, 4))
    assert r.iloc[0]["motivo"] == "gap_stop"
    assert r.iloc[0]["preco_saida"] == pytest.approx(.998)


def test_nao_empurra_entrada_para_depois_de_lacuna():
    b, a = cotacoes()
    b, a = b.drop(b.index[1]), a.drop(a.index[1])
    r = simular(b, a, pd.Series([1] + [0] * 6, index=b.index), pd.Series(.001, index=b.index))
    assert r.empty


def test_trailing_nao_pode_usar_fechamento_para_sair_no_passado_da_mesma_vela():
    b, a = cotacoes()
    b.loc[b.index[1], ["abertura", "maxima", "minima", "fechamento"]] = [1., 1.004, .999, 1.004]
    b.loc[b.index[2], ["abertura", "maxima", "minima", "fechamento"]] = [1.003, 1.004, 1.001, 1.003]
    r = simular(b, a, pd.Series([1] + [0] * 7, index=b.index), pd.Series(.001, index=b.index), RegraSaida(1.5, None, None, 2, 1))
    assert r.iloc[0]["saida_em"] == b.index[3]
    assert r.iloc[0]["preco_saida"] == pytest.approx(1.002)


def test_operacao_aberta_nao_e_lucro_realizado_nem_rotulo_de_treino():
    b, a = cotacoes()
    r = simular(b, a, pd.Series([1] + [0] * 7, index=b.index), pd.Series(.001, index=b.index), RegraSaida(10, None, None))
    assert r.iloc[0]["motivo"] == "aberta"
    assert np.isnan(r.iloc[0]["pips_bidask"])
    assert medir(r)["abertas"] == 1
    assert disponiveis_para_treino(r, pd.Timestamp("2026-08-01", tz="UTC")).empty


def test_modelo_so_recebe_resultado_depois_do_encerramento_e_purga_fronteira():
    b, a = cotacoes()
    r = simular(b, a, pd.Series([1] + [0] * 7, index=b.index), pd.Series(.001, index=b.index), RegraSaida(minutos=3))
    assert disponiveis_para_treino(r, b.index[4]).empty
    assert len(disponiveis_para_treino(r, b.index[5])) == 1


def test_carteira_escolhe_score_e_bloqueia_sobreposicao_sem_escolher_por_lucro():
    t = pd.Timestamp("2026-07-01", tz="UTC")
    r = pd.DataFrame({"sinal_em": [t, t, t + pd.Timedelta(minutes=1)],
                      "saida_em": [t + pd.Timedelta(minutes=5)] * 3,
                      "score": [.8, .9, .99], "estrategia": ["a", "b", "c"], "pips_bidask": [20, -5, 30]})
    assert uma_carteira(r)["estrategia"].tolist() == ["b"]


def test_alinhamento_nao_inventa_ask_e_rejeita_spread_negativo():
    b, a = cotacoes()
    a = a.drop(a.index[2])
    a.loc[a.index[0], "abertura"] = .99
    rb, ra, audit = conferir_cotacoes(b, a)
    assert len(rb) == len(ra) == 6
    assert audit["invalidos"] == 1
