"""Variantes ao vivo: só dados depois do registro, regras exatamente como declaradas e comparação pareada com o motor."""

from datetime import timedelta

import numpy as np
import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.e9.variantes import REGISTRO, apostas_reversao, filtrar_motor, placar_do_dia
from mneme.motor.diario import Diario
from test_e9_dossie import INICIO, decisao, velas
from test_e9_mapa import mercado


def test_registro_fixo():
    assert REGISTRO["registrado_em"].startswith("2026-11-15") and set(REGISTRO["variantes"]) == {"V1a", "V1b", "V2", "V3", "V4"}


def test_reversao_aposta_contra_a_ultima_vela_e_respeita_o_registro():
    v = mercado(n=3000)
    desde = v.index[1000]
    a = apostas_reversao(v, "X", desde, forte=False)
    assert (pd.DatetimeIndex(a["tempo"]) >= desde).all()
    corpo = np.sign((v["fechamento"] - v["abertura"]).reindex(pd.DatetimeIndex(a["tempo"])).to_numpy())
    assert len(a) > 100 and (a["direcao"].to_numpy() == -corpo).all()
    gaps = np.diff(pd.DatetimeIndex(a["tempo"]).as_unit("ns").asi8) // 60_000_000_000
    assert (gaps >= 7).all()  # uma por vez: atraso de 1 + expiração de 5 + 1


def test_reversao_forte_e_um_subconjunto():
    v = mercado(n=3000)
    todas = apostas_reversao(v, "X", v.index[200], forte=False)
    fortes = apostas_reversao(v, "X", v.index[200], forte=True)
    assert 0 < len(fortes) < len(todas)


def test_filtros_do_motor(tmp_path):
    d = Diario(tmp_path / "diario.db")
    base = pd.Timestamp(INICIO) + pd.Timedelta(days=1)
    for i, (ativo, noticia) in enumerate([("SOLUSDT", None), ("ETHUSDT", -1), ("ETHUSDT", 1), ("BTCUSDT", None)]):
        decisao(d, ativo, base + pd.Timedelta(minutes=10 * i), 1, "ganho", noticia=noticia)
    d.con.close()
    from mneme.e9.variantes import decisoes_motor
    m = decisoes_motor(tmp_path / "diario.db", base - pd.Timedelta(minutes=1))
    assert len(m) == 4
    assert len(filtrar_motor(m, "V2")) == 0  # as decisões de teste são 1m→5m
    assert set(filtrar_motor(m, "V3")["chave"]) == {"ETHUSDT", "BTCUSDT"}
    assert len(filtrar_motor(m, "V4")) == 3  # tira a de notícia contra a direção


def test_placar_do_dia_compara_com_o_motor(tmp_path):
    v = velas(2 * 1440)
    ArmazemVelas(tmp_path / "mercado").gravar("ETHUSDT", v, INICIO + timedelta(days=30))
    d = Diario(tmp_path / "diario.db")
    base = pd.Timestamp(INICIO) + pd.Timedelta(days=1)
    for i in range(30):
        decisao(d, "ETHUSDT", base + pd.Timedelta(minutes=9 * i), 1 if i % 2 else -1, "ganho" if i % 3 else "perda")
    d.con.close()
    p = placar_do_dia(tmp_path / "diario.db", ArmazemVelas(tmp_path / "mercado"), ativos=("ETHUSDT",), desde=base - pd.Timedelta(minutes=1),
                      ate=base + pd.Timedelta(hours=6))
    assert set(p) >= {"motor", "V1a", "V1b", "V2", "V3", "V4"}
    assert p["motor"]["apostas"] == 30 and "pareado_contra_motor" in p["V3"]


def test_nota_das_variantes_no_vault(tmp_path):
    import json
    from mneme.vault import Vault, escrever_variantes_e9

    caminho = tmp_path / "placar.json"
    caminho.write_text(json.dumps({"registro": REGISTRO, "desde": "2026-11-15", "ate": "2026-11-16", "amostra_minima_por_variante": 9000,
                                   "motor": {"apostas": 10, "acerto": 0.6, "expectativa": {"0.85": 0.05}, "expectativa_ic95": {"0.85": [-0.1, 0.2]}},
                                   "V1a": {"apostas": 0}}))
    v = Vault(tmp_path / "vault", relogio=lambda: pd.Timestamp("2026-11-16", tz="UTC").to_pydatetime())
    v.iniciar()
    assert escrever_variantes_e9(v, caminho) == 1
    texto = next(v.raiz.rglob("E9 - variantes ao vivo.md")).read_text(encoding="utf-8")
    assert "acompanhamento" in texto and "V1a" in texto and "9000" in texto
    assert escrever_variantes_e9(v, tmp_path / "nao_existe.json") == 0
