"""C1: a política do motor é reproduzida fielmente, o candidato só aprende na exploração, o filtro só abstém e o bloco de
confirmação só pode ser aberto uma vez."""

import numpy as np
import pandas as pd
import pytest

from mneme.e9.confirmacao import (CONFIRMACAO, EXPLORACAO_ATE, PROTOCOLO_C1, BlocoJaAberto, aplicar_filtro, lacrar, politica_motor,
                                  treinar_candidato)
from mneme.laboratorio.confluencia import decidir, grade_de_sinais
from test_e9_mapa import mercado


def modelo_sintetico(tecnicas):
    r = np.random.default_rng(0)
    return {"tecnicas": list(tecnicas), "pesos": list(r.normal(0, 0.3, len(tecnicas))), "intercepto": 0.01, "corte": 0.02}


def test_politica_do_motor_e_a_mesma_decisao_do_motor():
    v = mercado(n=8000)
    sinais = grade_de_sinais(v, 5)
    modelo = modelo_sintetico(sinais.columns)
    tempos, direcao = politica_motor(v, modelo, candle=5, expiracao=5, sinais=sinais, uma_por_vez_=False)
    esperado = {t: decidir(modelo, sinais.loc[t]) for t in sinais.index}
    esperado = {t: d["direcao"] for t, d in esperado.items() if d is not None}
    assert dict(zip(tempos, direcao)) == esperado


def test_candidato_so_ve_a_exploracao():
    v = mercado(n=30_000)
    corte = v.index[20_000]
    a = treinar_candidato(v, 5, ate=corte)
    alterado = v.copy()
    alterado.loc[alterado.index >= corte, ["abertura", "maxima", "minima", "fechamento"]] *= 1.5  # muda tudo depois do corte
    b = treinar_candidato(alterado, 5, ate=corte)
    assert a.limiar == b.limiar and a.impressao == b.impressao


def test_filtro_so_faz_abster():
    base = pd.DataFrame({"ativo": "X", "tempo": pd.date_range("2026-03-01", periods=6, freq="h", tz="UTC"), "direcao": [1, -1, 1, 1, -1, 1],
                         "retorno": [0.01, -0.01, 0.02, -0.01, 0.01, 0.0]})
    risco = pd.Series([0.9, 0.1, 0.5, 0.95, 0.2, 0.5], index=base["tempo"])
    f = aplicar_filtro(base, risco, acima_de=0.8)
    assert list(f["direcao"]) == [0, -1, 1, 0, -1, 1]
    assert (f[["ativo", "tempo", "retorno"]] == base[["ativo", "tempo", "retorno"]]).all().all()


def test_bloco_de_confirmacao_so_abre_uma_vez(tmp_path):
    lacrar(tmp_path, PROTOCOLO_C1)
    with pytest.raises(BlocoJaAberto):
        lacrar(tmp_path, PROTOCOLO_C1)


def test_protocolo_respeita_os_blocos_da_etapa_0():
    assert EXPLORACAO_ATE == pd.Timestamp("2026-02-01", tz="UTC") and CONFIRMACAO == (pd.Timestamp("2026-02-01", tz="UTC"), pd.Timestamp("2026-08-01", tz="UTC"))
    assert PROTOCOLO_C1["variantes_max_para_confirmar"] == 2 and set(PROTOCOLO_C1["variantes"]) == {"V1", "V2", "V3", "V4"}
