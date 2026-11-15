"""Leitura do gráfico para o card: as linhas que o motor lê, a probabilidade do modelo dele e o cone de onde o preço pode ir."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from mneme.digitais.leitura_grafico import leitura
from mneme.laboratorio.confluencia import decidir, grade_de_sinais

sys.path.insert(0, str(Path(__file__).parent))
from test_e9_mapa import mercado  # noqa: E402


def modelo(v):
    tecnicas = list(grade_de_sinais(v, 5).columns)
    r = np.random.default_rng(0)
    return {"tecnicas": tecnicas, "pesos": list(r.normal(0, 0.3, len(tecnicas))), "intercepto": 0.02, "corte": 0.03}


def test_leitura_tem_velas_linhas_e_previsao():
    v = mercado(n=6000)
    m = modelo(v)
    agora = v.index[-1] + pd.Timedelta(minutes=1, seconds=10)
    r = leitura(v, candle=5, expiracao=5, modelo=m, agora=agora)
    assert len(r["velas"]) == 72 and r["velas"][-1]["t"] < agora.isoformat()
    precos = [x for c in r["velas"] for x in (c["max"], c["min"])]
    lo, hi = min(precos), max(precos)
    for nome in ("suporte", "resistencia"):
        assert r["linhas"][nome] is None or lo * 0.9 < r["linhas"][nome] < hi * 1.1
    assert {"lta", "ltb", "fibonacci", "vwap", "poc"} <= set(r["linhas"])
    p = r["previsao"]
    assert 0 <= p["prob_sobe"] <= 1 and p["direcao"] in ("CALL", "PUT", None)
    cone = p["cone"]
    assert cone[0]["hi68"] - cone[0]["lo68"] < cone[-1]["hi68"] - cone[-1]["lo68"]  # abre com o tempo
    assert all(c["lo95"] <= c["lo68"] <= c["hi68"] <= c["hi95"] for c in cone)


def test_probabilidade_e_a_mesma_conta_do_motor():
    v = mercado(n=6000)
    m = modelo(v)
    r = leitura(v, candle=5, expiracao=5, modelo=m, agora=v.index[-1] + pd.Timedelta(minutes=1))
    sinais = grade_de_sinais(v, 5)
    d = decidir({**m, "corte": 0.0}, sinais.iloc[-1])
    assert abs(r["previsao"]["prob_sobe"] - d["prob_sobe"]) < 1e-9
    assert r["previsao"]["vela"] == sinais.index[-1].isoformat()


def test_nada_do_futuro():
    """Velas depois do instante pedido não mudam nada da leitura."""
    v = mercado(n=6000)
    m = modelo(v)
    agora = v.index[5000]
    a = leitura(v[v.index < agora], candle=5, expiracao=5, modelo=m, agora=agora)
    b = leitura(v, candle=5, expiracao=5, modelo=m, agora=agora)
    assert a == b


def test_previsao_anterior_mostra_o_que_aconteceu():
    v = mercado(n=6000)
    r = leitura(v, candle=5, expiracao=5, modelo=modelo(v), agora=v.index[-1] + pd.Timedelta(minutes=1))
    ant = r["anterior"]
    assert ant is not None and ant["realizado"] is not None
    assert ant["dentro_68"] in (True, False)


def test_degraus_contagem_e_cenarios():
    v = mercado(n=6000)
    r = leitura(v, candle=5, expiracao=5, modelo=modelo(v), agora=v.index[-1] + pd.Timedelta(minutes=1))
    degraus = r["linhas"]["degraus"]
    assert len(degraus) == len(r["velas"]) and set(degraus[0]) == {"t", "suporte", "resistencia"}
    c = r["previsao"]["tecnicas"]
    assert c["alta"] + c["baixa"] <= c["total"] and c["total"] > 10
    cen = r["previsao"]["cenarios"]
    assert len(cen) == 5 and all(len(x) == len(r["previsao"]["cone"]) for x in cen)
    # Os cenários não mudam entre consultas da mesma vela (semente fixa pela vela).
    r2 = leitura(v, candle=5, expiracao=5, modelo=modelo(v), agora=v.index[-1] + pd.Timedelta(minutes=1, seconds=40))
    assert r2["previsao"]["cenarios"] == cen
