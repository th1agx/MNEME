"""Entrega 4: calendário, metodologias, dataset, modelos e previsões ao vivo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from mneme import metodologias as met
from mneme.dados.armazem import ArmazemVelas
from mneme.dados.calendario import fomc_da_pagina, semana_do_feed
from mneme.dados.eventos import ArmazemEventos
from mneme.dados.velas import tabela
from mneme.laboratorio.dataset import alvos, amostrar, colunas_de, construir
from mneme.laboratorio.avaliacao import (brier, calibrar_com_passado, metricas, por_grupo, precisao_e_revocacao, regimes, retornos_digitais,
                                         selecionar_com_passado, separar_selado)
from mneme.laboratorio.previsao import (Previsoes, _lgb_c, carregar_artefato, erro_calibracao, medir, meta_rotulo, prever_direcao, prever_regressao,
                                        treinar_artefato)
from mneme.leitura import atributos
from mneme.previsor import Previsor, carregar_todos, placar

INICIO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def passeio(n=8000, semente=1, inicio=INICIO) -> pd.DataFrame:
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.001, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, 0.0005, n)) * f
    volume = g.uniform(10, 100, n)
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + folga, "minima": np.minimum(a, f) - folga, "fechamento": f, "volume": volume,
                         "volume_comprador": volume * g.uniform(0, 1, n), "negocios": g.integers(1, 50, n)},
                        index=pd.date_range(inicio, periods=n, freq="1min", tz="UTC", name="abertura_em"))


def funding_falso(n=120):
    return pd.DataFrame({"ocorrido_em": pd.date_range(INICIO - timedelta(days=30), periods=n, freq="8h", tz="UTC"),
                         "funding": np.random.default_rng(0).normal(1e-4, 5e-5, n)})


# ---------- calendário ----------

PAGINA = """<div>2026 FOMC Meetings</div><div class="m"><strong>January</strong></div><div>27-28</div>
<div><strong>Apr/May</strong></div><div>28-29*</div>
<div><strong>Oct/Nov</strong></div><div>30-1</div>
<h3>2025 FOMC Meetings</h3><strong>December</strong><span>9-10*</span><strong>March</strong> <span>5 (notation vote)</span>"""


def test_fomc_le_o_ultimo_dia_as_14h_de_nova_york():
    eventos = fomc_da_pagina(PAGINA)
    momentos = [e["ocorrido_em"] for e in eventos]
    assert pd.Timestamp("2026-01-28 19:00", tz="UTC") in momentos  # inverno: UTC-5
    assert pd.Timestamp("2026-04-29 18:00", tz="UTC") in momentos  # verão: UTC-4
    assert pd.Timestamp("2026-11-01 19:00", tz="UTC") in momentos  # virou o mês e o horário de verão já acabou às 14h
    assert pd.Timestamp("2025-12-10 19:00", tz="UTC") in momentos
    assert len(momentos) == 4  # voto sem reunião de dois dias não entra
    assert momentos == sorted(momentos)


FEED = b"""<?xml version="1.0" encoding="windows-1252"?><weeklyevents>
<event><title>CPI y/y</title><country>USD</country><date><![CDATA[11-10-2026]]></date><time><![CDATA[1:30pm]]></time><impact><![CDATA[High]]></impact><forecast><![CDATA[3.1%]]></forecast><previous><![CDATA[3.0%]]></previous></event>
<event><title>Holiday</title><country>JPY</country><date><![CDATA[11-03-2026]]></date><time><![CDATA[All Day]]></time><impact><![CDATA[Holiday]]></impact><forecast></forecast><previous></previous></event>
</weeklyevents>"""


def test_feed_le_evento_com_previsao_e_ignora_sem_hora():
    eventos = semana_do_feed(FEED, INICIO)
    assert len(eventos) == 1
    e = eventos[0]
    assert e["ocorrido_em"] == pd.Timestamp("2026-11-10 13:30", tz="UTC")
    assert (e["moeda"], e["impacto"], e["previsao"], e["anterior"]) == ("USD", "High", "3.1%", "3.0%")


def test_previsao_alterada_vira_nova_versao_e_a_igual_nao_duplica(tmp_path):
    a = ArmazemEventos(tmp_path)
    a.gravar("calendario", "GLOBAL", semana_do_feed(FEED, INICIO))
    a.gravar("calendario", "GLOBAL", semana_do_feed(FEED, INICIO + timedelta(hours=1)))
    a.gravar("calendario", "GLOBAL", semana_do_feed(FEED.replace(b"3.1%", b"3.2%"), INICIO + timedelta(hours=2)))
    lido = a.ler("calendario", "GLOBAL")
    assert sorted(lido["previsao"]) == ["3.1%", "3.2%"]
    assert a.ler("calendario", "GLOBAL", como_de=pd.Timestamp("2026-11-10 13:30", tz="UTC"))["recebido_em"].min() == pd.Timestamp(INICIO)


# ---------- metodologias ----------

@pytest.fixture(scope="module")
def v15():
    v = passeio(6000).resample("15min", label="left", closed="left").agg(
        {"abertura": "first", "maxima": "max", "minima": "min", "fechamento": "last", "volume": "sum", "volume_comprador": "sum", "negocios": "sum"})
    return v.dropna()


@pytest.mark.parametrize("corte", [250, 300, 390])
def test_nenhuma_metodologia_olha_o_futuro(v15, corte):
    completo = met.evidencias(v15, atributos(v15)).iloc[corte]
    parcial_v = v15.iloc[:corte + 1]
    parcial = met.evidencias(parcial_v, atributos(parcial_v)).iloc[-1]
    for coluna in completo.index:
        a, b = completo[coluna], parcial[coluna]
        assert (pd.isna(a) and pd.isna(b)) or float(a) == pytest.approx(float(b), rel=1e-9, abs=1e-9), coluna


def _velas(h, l, c=None, a=None):
    h, l = np.array(h, float), np.array(l, float)
    c = (h + l) / 2 if c is None else np.array(c, float)
    a = np.concatenate([[c[0]], c[:-1]]) if a is None else np.array(a, float)
    return pd.DataFrame({"abertura": a, "maxima": h, "minima": l, "fechamento": c, "volume": 10.0, "volume_comprador": 5.0, "negocios": 1},
                        index=pd.date_range(INICIO, periods=len(h), freq="15min", tz="UTC"))


def test_fibonacci_mede_a_retracao_da_ultima_perna():
    # Fundo em 90, topo em 200 e queda contínua até 132: como nenhum fundo novo se confirmou, a perna ainda é a de alta.
    h = [110, 108, 105, 100, 101, 102, 150, 200, 199, 180, 170, 160, 155, 150, 145, 140, 138, 136]
    l = [104, 102, 100, 99, 95, 90, 100, 150, 170, 165, 155, 150, 145, 140, 138, 136, 134, 132]
    c = [106, 104, 102, 100, 100, 100, 140, 190, 175, 170, 160, 155, 150, 145, 140, 138, 135, 132]
    v = _velas(h, l, c)
    x = met.fibonacci(v, pd.Series(5.0, index=v.index)).iloc[-1]
    assert x["fib_sentido"] == 1
    assert x["fib_retracao"] == pytest.approx((200 - 132) / (200 - 90), abs=0.001)
    assert x["fib_zona_dourada"] == 1
    assert x["fib_dist_618"] == pytest.approx((132 - (200 - 0.618 * 110)) / 5, abs=0.001)


def test_fvg_aparece_e_e_invalidado_por_fechamento_alem_do_buraco():
    v = _velas([10, 11, 15, 15, 15, 11], [9, 10, 13, 13, 13, 9], [10, 11, 14, 14, 14, 9.5])
    x = met.fair_value_gaps(v, pd.Series(1.0, index=v.index))
    assert x["fvg_alta_dist"].iloc[2] == pytest.approx(14 - 13)  # mínima 13 acima da máxima 10 de duas velas antes
    assert pd.isna(x["fvg_alta_dist"].iloc[5])  # fechou abaixo do início do buraco


def test_order_block_e_a_ultima_vela_contraria_antes_do_rompimento():
    v = _velas([11, 12, 11, 15, 15, 15], [9, 10, 9, 10, 13, 8], c=[11, 11, 10, 14, 14, 8.5], a=[10, 11, 11, 10, 14, 14])
    rompeu = pd.Series([0, 0, 0, 1, 0, 0], index=v.index)
    x = met.order_blocks(v, pd.Series(1.0, index=v.index), rompeu)
    assert x["ob_alta_dist"].iloc[4] == pytest.approx(14 - 11)  # vela 2 fechou em baixa; a zona começa na máxima dela
    assert pd.isna(x["ob_alta_dist"].iloc[5])  # fechou abaixo da mínima da zona


def test_ichimoku_usa_a_nuvem_de_26_velas_atras():
    v = _velas(np.linspace(100, 200, 120) + 1, np.linspace(100, 200, 120) - 1)
    x = met.ichimoku(v, pd.Series(1.0, index=v.index))
    assert x["ichi_nuvem_pos"].iloc[-1] == 1  # em alta, o preço fica acima da nuvem
    assert pd.isna(x["ichi_nuvem_pos"].iloc[60])  # span B precisa de 52 velas, mais 26 de deslocamento


def test_varredura_de_liquidez_fecha_de_volta_para_dentro():
    v = _velas([11, 12, 13, 12, 11, 12, 15, 12], [9, 10, 11, 10, 9, 10, 11, 10], c=[10, 11, 12, 11, 10, 11, 12, 11])
    a = pd.DataFrame({"resistencia": 13.0, "suporte": 9.0, "consolidacao": 0, "atr_14": 1.0}, index=v.index)
    assert met.eventos_de_liquidez(v, a)["liq_varredura"].iloc[6] == -1  # furou 13, fechou abaixo


# ---------- dataset ----------

@pytest.fixture(scope="module")
def base():
    v = passeio(8000)
    return v, passeio(8000, 2)


@pytest.mark.parametrize("corte", [6000, 7000, 7999])
def test_dataset_nao_olha_o_futuro(base, corte):
    v, ref = base
    eventos = pd.Series(pd.to_datetime(["2026-01-03 19:00", "2026-01-06 19:00"], utc=True))
    fin = funding_falso()
    completo = construir(v, fin, ref, eventos).iloc[corte]
    parcial = construir(v.iloc[:corte + 1], fin[fin["ocorrido_em"] <= v.index[corte]], ref.iloc[:corte + 1], eventos).iloc[-1]
    for coluna in completo.index:
        a, b = completo[coluna], parcial[coluna]
        assert (pd.isna(a) and pd.isna(b)) or float(a) == pytest.approx(float(b), rel=1e-7, abs=1e-7), coluna


def test_dataset_tem_todas_as_familias(base):
    v, ref = base
    x = construir(v, funding_falso(), ref, pd.Series(pd.to_datetime(["2026-01-03 19:00"], utc=True)))
    for prefixo in ("v_", "m_", "f_", "c_", "d_", "t_", "e_"):
        assert colunas_de(x, (prefixo,)), prefixo


def test_vela_grande_so_vale_depois_de_fechar():
    v = passeio(3000)
    alterado = v.copy()
    alterado.iloc[2999, alterado.columns.get_indexer(["fechamento", "maxima"])] *= 3  # última vela do bloco de 15 min em aberto
    a, b = construir(v), construir(alterado)
    coluna = "v_15min_rsi_14"
    assert a[coluna].iloc[:2999].equals(b[coluna].iloc[:2999])


def test_evento_conta_o_tempo_ate_e_desde():
    v = passeio(100)
    evento = v.index[50] + timedelta(minutes=1)  # o instante em que a vela 50 fecha
    x = construir(v, eventos=pd.Series([evento]))
    assert x["e_ate_evento"].iloc[40] == 10
    assert x["e_desde_evento"].iloc[60] == 10


def test_alvo_usa_a_entrada_e_a_saida_do_backtest():
    v = passeio(50)
    y = alvos(v, 5).iloc[10]
    assert y["retorno"] == pytest.approx(v["fechamento"].iloc[15] / v["abertura"].iloc[11] - 1)
    assert y["sobe"] == float(v["fechamento"].iloc[15] > v["abertura"].iloc[11])


def test_amostra_fica_na_grade_e_tira_quem_nao_tem_alvo(base):
    v, _ = base
    x, y = amostrar(construir(v), alvos(v, 15), 15)
    assert ((x.index.minute + 1) % 15 == 0).all()
    assert y["sobe"].notna().all() and len(x) == len(y)
    assert x.index.max() + timedelta(minutes=15) <= v.index.max()


# ---------- modelos ----------

def _ruido(n=5000, semente=0):
    g = np.random.default_rng(semente)
    return pd.DataFrame(g.normal(size=(n, 6)), columns=list("abcdef")), pd.Series(g.integers(0, 2, n).astype(float))


def test_em_ruido_nenhum_modelo_vence():
    x, y = _ruido()
    for r in prever_direcao(x, y, 0.5405):
        assert r.acerto == pytest.approx(0.5, abs=0.035) and r.auc == pytest.approx(0.5, abs=0.05) and r.p_valor > 0.5


def test_com_sinal_todos_os_modelos_acham():
    x, _ = _ruido()
    y = (x["a"] + np.random.default_rng(1).normal(0, 0.5, len(x)) > 0).astype(float)
    for r in prever_direcao(x, y, 0.5405):
        assert r.acerto > 0.8 and r.auc > 0.9, r.modelo


def test_erro_de_calibracao_distingue_certo_de_errado():
    g = np.random.default_rng(0)
    p = g.uniform(0, 1, 50_000)
    real = (g.uniform(0, 1, 50_000) < p).astype(float)
    assert erro_calibracao(p, real) < 0.02
    assert erro_calibracao(np.clip(p * 0.5 + 0.5, 0, 1), real) > 0.2


def test_medir_escolhe_os_confiantes_com_corte_do_passado():
    # Bloco 1 define o corte da distância (0,1). No bloco 2, só 0,9 e 0,1 passam; o acerto geral conta tudo.
    prob = np.array([0.6, 0.4, 0.55, 0.45, 0.9, 0.1, 0.51, 0.49])
    real = np.array([1, 0, 0, 1, 1, 0, 0, 1], float)
    r = medir("x", Previsoes(prob, real, np.arange(8), [4, 4]), 0.5, confianca=0.5)
    assert r.previsoes_confiantes == 2 and r.acerto_confiante == 1.0 and r.acerto == 0.5
    assert r.metricas_confiantes["operacoes"] == 2


# ---------- seleção e calibração só com o passado ----------

def test_futuro_alterado_nao_muda_selecao_passada():
    g = np.random.default_rng(0)
    valores = g.uniform(0, 1, 1000)
    blocos = [250, 250, 250, 250]
    original = selecionar_com_passado(valores, blocos, 0.2)
    alterado = valores.copy()
    alterado[750:] = 99  # futuro extremo
    mudado = selecionar_com_passado(alterado, blocos, 0.2)
    assert (original[:750] == mudado[:750]).all()
    assert not original[:250].any()  # sem passado, sem seleção


def test_corte_calculado_com_todo_o_periodo_daria_outro_resultado():
    """Mostra o erro corrigido: com o mercado mudando de nível, o corte global escolhe o que o passado não permitiria."""
    valores = np.concatenate([np.full(500, 0.1), np.full(500, 0.9)])
    global_ = valores >= np.quantile(valores, 0.8)
    passado = selecionar_com_passado(valores, [250, 250, 250, 250], 0.2)
    assert not global_[250:500].any() and passado[250:500].all()


def test_calibracao_nao_usa_o_bloco_que_esta_calibrando():
    g = np.random.default_rng(1)
    prob = g.uniform(0, 1, 800)
    real = (g.uniform(0, 1, 800) < prob).astype(float)
    a, validas = calibrar_com_passado(prob, real, [200, 200, 200, 200])
    real2 = real.copy()
    real2[600:] = 1 - real2[600:]
    b, _ = calibrar_com_passado(prob, real2, [200, 200, 200, 200])
    assert not validas[:200].any() and validas[200:].all()
    np.testing.assert_array_equal(a[:600], b[:600])
    np.testing.assert_array_equal(a[600:], b[600:])


def test_metricas_com_valores_conhecidos():
    m = metricas(np.array([0.85, 0.85, -1.0, 0.85, -1.0]))
    assert m.operacoes == 5 and m.acerto == 0.6
    assert m.expectativa == pytest.approx(0.11)
    assert m.fator_de_lucro == pytest.approx(2.55 / 2)
    assert m.resultado_total == pytest.approx(0.55)
    assert m.pior_queda == pytest.approx(-1.15)
    assert m.sharpe > 0 and m.sortino > m.sharpe


def test_acuracia_alta_nao_quer_dizer_lucro():
    """Com payout de 50%, acertar 60% perde dinheiro: o empate é 66,7%."""
    ganhou = np.array([True] * 60 + [False] * 40)
    m = metricas(retornos_digitais(ganhou, 0.5))
    assert m.acerto == 0.6 and m.expectativa < 0 and m.fator_de_lucro < 1


def test_metricas_vazias_nao_quebram():
    assert metricas(np.array([])).operacoes == 0


def test_brier_e_precisao():
    assert brier(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 0
    assert brier(np.array([0.5, 0.5]), np.array([1.0, 0.0])) == 0.25
    assert precisao_e_revocacao(np.array([True, True, False, False]), np.array([1, 0, 1, 0])) == (0.5, 0.5)


def test_regime_e_por_grupo():
    x = pd.DataFrame({"v_60min_tendencia": [1, -1, 0], "v_60min_volatilidade_percentil": [0.9, 0.1, 0.5]})
    assert regimes(x).tolist() == ["alta · volátil", "baixa · calmo", "sem tendência · volátil"]
    grupos = por_grupo(np.array([1.0, -1.0, 1.0]), np.array(["a", "b", "a"]))
    assert grupos["a"]["operacoes"] == 2 and grupos["b"]["acerto"] == 0


def test_area_selada_fica_fora_do_desenvolvimento():
    indice = pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC")
    desenvolvimento, selado = separar_selado(indice, pd.Timestamp("2026-01-08", tz="UTC"))
    assert desenvolvimento.sum() == 7 and selado.sum() == 3 and not (desenvolvimento & selado).any()


def test_regressao_compara_com_a_referencia():
    g = np.random.default_rng(0)
    x = pd.DataFrame(g.normal(size=(5000, 3)), columns=list("abc"))
    y = x["a"] + 0.5 * x["b"] ** 2 + g.normal(0, 0.1, 5000)
    r = prever_regressao(x, y, x["a"])
    assert r["r2_modelo"] > r["r2_referencia"] > 0.3 and r["ganho_sobre_referencia"] > 0


def test_meta_rotulo_nao_inventa_vantagem_em_ruido():
    x, y = _ruido()
    r = meta_rotulo(x, y, 0.5405)
    assert r["acerto_selecionados"] == pytest.approx(0.5, abs=0.05) and r["p_valor"] > 0.3


# ---------- artefato e previsor ----------

def _modelo(tmp_path, par="BTCUSDT", h=15, n=3000):
    g = np.random.default_rng(0)
    v = passeio(8000)
    x, y = amostrar(construir(v, funding_falso(), passeio(8000, 2), pd.Series(pd.to_datetime(["2026-01-03 19:00"], utc=True))), alvos(v, h), h)
    return treinar_artefato(tmp_path / "modelos", par, h, x, y["sobe"], "dados", "abc", lambda: _lgb_c().set_params(n_estimators=10, min_child_samples=20))


def test_artefato_confere_o_hash(tmp_path):
    a = _modelo(tmp_path)
    assert carregar_artefato(a.caminho).manifesto["id"] == a.manifesto["id"]
    (a.caminho / "modelo.txt").write_text("adulterado", encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_artefato(a.caminho)
    assert carregar_todos(tmp_path / "modelos") == []


def _preparar_armazem(tmp_path, v):
    armazem = ArmazemVelas(tmp_path)
    linhas = v.reset_index().assign(volume_cotacao=1.0, recebido_em=None, origem="arquivo").to_dict("records")
    fim = v.index[-1].to_pydatetime() + timedelta(minutes=1)
    for par in ("BTCUSDT", "ETHUSDT"):
        armazem.gravar(par, tabela(linhas), fim)
    return fim


class Fora:
    def semana(self, *_):
        raise ValueError("fora")

    def fomc(self, *_):
        raise ValueError("fora")

    def funding_historico(self, *_):
        raise ValueError("fora")


def test_previsor_grava_uma_vez_e_o_placar_confere(tmp_path):
    artefato = _modelo(tmp_path)
    v = passeio(8000)
    n_hoje = int((v.index.hour * 60 + v.index.minute + 1)[7000:].tolist().index(next(m for m in (v.index.hour * 60 + v.index.minute + 1)[7000:] if m % 15 == 0))) + 7000
    corte = v.iloc[:n_hoje + 1]
    agora = _preparar_armazem(tmp_path, corte)
    relogio = {"t": agora}
    prev = Previsor(tmp_path, [artefato], lambda: relogio["t"], Fora(), Fora())
    prev.atualizar_fontes()  # fonte fora do ar não derruba
    assert prev.ciclo() == 1
    assert prev.ciclo() == 0
    gravada = prev.eventos.ler("previsoes", "BTCUSDT").iloc[0]
    assert gravada["ocorrido_em"] == corte.index[-1]
    assert 0 <= gravada["prob_sobe"] <= 1 and gravada["direcao"] in (1, -1)
    assert pd.Timestamp(gravada["recebido_em"]) >= gravada["ocorrido_em"] + timedelta(minutes=1)  # só depois da vela fechar

    # Ao reiniciar, não repete.
    assert Previsor(tmp_path, [artefato], lambda: relogio["t"], Fora(), Fora()).ciclo() == 0

    aberto = placar(tmp_path, ["BTCUSDT"])[0]
    assert (aberto["abertas"], aberto["conferidas"]) == (1, 0)
    resto = v.iloc[n_hoje + 1:n_hoje + 16]
    ArmazemVelas(tmp_path).gravar("BTCUSDT", tabela(resto.reset_index().assign(volume_cotacao=1.0, recebido_em=None, origem="arquivo").to_dict("records")),
                                  resto.index[-1].to_pydatetime() + timedelta(minutes=1))
    fechado = placar(tmp_path, ["BTCUSDT"])[0]
    assert fechado["conferidas"] == 1
    subiu = v["fechamento"].iloc[n_hoje + 15] > v["abertura"].iloc[n_hoje + 1]
    assert fechado["certas"] == int(subiu == (gravada["direcao"] == 1))


def test_previsor_entrega_noticia_sem_ocorrido_em_ao_modelo_com_atributo_n(tmp_path):
    v = passeio(8000)
    n_hoje = int((v.index.hour * 60 + v.index.minute + 1)[7000:].tolist().index(
        next(m for m in (v.index.hour * 60 + v.index.minute + 1)[7000:] if m % 15 == 0)
    )) + 7000
    corte = v.iloc[:n_hoje + 1]
    agora = _preparar_armazem(tmp_path, corte)
    vela = corte.index[-1]
    chegada = vela.to_pydatetime() + timedelta(minutes=1)
    ArmazemEventos(tmp_path).gravar("noticias", "GLOBAL", [{
        "id": "noticia-corvo-1", "publicado_em": vela - timedelta(days=2), "ocorrido_em": None,
        "recebido_em": chegada, "fonte": "fed", "titulo": "Bitcoin ETF inflows hit new record",
        "resumo": "", "ativos": ["BTC"], "sentimento": 1, "tipo": "reportagem", "suspeito": False,
    }])

    class ModeloComNoticias:
        manifesto = {"id": "teste-noticias", "par": "BTCUSDT", "horizonte": 15, "colunas": ["n_mencoes"]}

        def __init__(self):
            self.entrada = None

        def prever(self, atributos):
            self.entrada = atributos.copy()
            return np.array([0.6]), np.array([0.6])

    modelo = ModeloComNoticias()
    previsor = Previsor(tmp_path, [modelo], lambda: agora, Fora(), Fora())

    assert previsor.ciclo() == 1
    assert modelo.entrada is not None
    assert modelo.entrada["n_mencoes"].iloc[0] == 1


def test_previsor_nao_preve_com_dado_velho(tmp_path):
    artefato = _modelo(tmp_path)
    agora = _preparar_armazem(tmp_path, passeio(7000))
    prev = Previsor(tmp_path, [artefato], lambda: agora + timedelta(minutes=30), Fora(), Fora())
    assert prev.ciclo() == 0
