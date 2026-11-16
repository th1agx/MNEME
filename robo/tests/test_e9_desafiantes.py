"""Desafiantes do ETH: só decisões depois do registro, cada um um subconjunto da base, comparado no mesmo período."""

import pandas as pd

from mneme.e9.desafiantes import BASE, placar_geral, selecionar, ler_decisoes
from mneme.motor.diario import Diario


def reg(d, estrategia, vela, acao="CALL", forca=0.07, resultado="ganho"):
    v = pd.Timestamp(vela)
    chave = f"{estrategia}|{v.isoformat()}"
    d.registrar(chave=chave, estrategia=estrategia, mercado="cripto", ativo=estrategia.split("|")[0], modalidade="expiracao_fixa", vela=v,
                decidido_em=v + pd.Timedelta(minutes=1), latencia_s=1.0, direcao=1 if acao == "CALL" else -1, forca=forca, expectativa=0.0,
                evidencia={}, motivo="", motivos_recusa=(), contexto=(),
                sinal={"acao": acao, "entrada_em": (v + pd.Timedelta(minutes=2)).isoformat(), "expiracao_min": 5}, tipo="operada", tamanho=1.0)
    if resultado:
        d.encerrar(chave, {"resultado": resultado, "pnl": 0.0, "preco_entrada": 1.0, "preco_saida": 1.0, "encerrado_por": "expiracao"}, v + pd.Timedelta(minutes=8))


def test_filtros_e_registro(tmp_path):
    d = Diario(tmp_path / "diario.db")
    reg(d, BASE, "2026-11-16T12:00:00Z")                      # antes do registro: fora
    reg(d, BASE, "2026-11-17T12:00:00Z", forca=0.05)           # 9h em Brasília, fraca
    reg(d, BASE, "2026-11-17T22:00:00Z", forca=0.08, resultado="perda")  # 19h em Brasília: D1 tira
    reg(d, BASE, "2026-11-17T13:00:00Z", forca=0.09)
    reg(d, "BTCUSDT|expiracao_fixa|1m|5m", "2026-11-17T13:00:00Z")
    reg(d, "SOLUSDT|expiracao_fixa|1m|5m", "2026-11-17T13:00:00Z")
    reg(d, "BTCUSDT|expiracao_fixa|1m|5m", "2026-11-17T12:00:00Z", acao="PUT")  # direção oposta: D3 não aceita
    reg(d, "SOLUSDT|expiracao_fixa|1m|5m", "2026-11-17T12:00:00Z")
    x = ler_decisoes(tmp_path / "diario.db")
    assert len(selecionar(x, "base")) == 3
    assert len(selecionar(x, "D1")) == 2
    assert len(selecionar(x, "D2")) == 2
    assert list(selecionar(x, "D3")["vela"]) == [pd.Timestamp("2026-11-17T13:00:00Z")]
    p = placar_geral(tmp_path / "diario.db")
    assert p["base"]["sinais"] == 3 and abs(p["base"]["acerto"] - 2 / 3) < 1e-9
    assert p["D1"]["acerto"] == 1.0 and abs(p["D1"]["diferenca_para_base"] - 1 / 3) < 1e-9
    assert p["D3"]["sinais"] == 1 and p["D3"]["fracao_da_base"] == 1 / 3


def test_sem_decisoes_novas(tmp_path):
    Diario(tmp_path / "diario.db")
    p = placar_geral(tmp_path / "diario.db")
    assert p["base"] == {"sinais": 0, "empates": 0} and p["D1"]["sinais"] == 0
