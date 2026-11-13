"""Dados de teste do quadro: um mercado pequeno e completo em disco, com diário, configuração e modelos de verdade."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.dados.eventos import ArmazemEventos
from mneme.dados.velas import tabela
from mneme.laboratorio.confluencia import NOMES
from mneme.motor.diario import Diario
from mneme.quadro.banco import Quadro
from mneme.quadro.coordenador import Coordenador

INICIO = datetime(2026, 11, 1, tzinfo=timezone.utc)
MINUTOS = 6 * 24 * 60
AGORA = INICIO + timedelta(minutes=MINUTOS)  # todas as velas fecharam
TECNICA = next(iter(NOMES.values()))
LIMITES = {"meta_dia_pct": 20, "perda_dia_pct": 10, "max_operacoes_dia": 200, "max_simultaneas_total": 100, "max_perdas_seguidas": 8,
           "drawdown_max_pct": 40, "idade_maxima_dados_min": 3}


def velas(n=MINUTOS, semente=0) -> pd.DataFrame:
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.0008, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, 0.05, n))
    vol = g.lognormal(3, 1, n)
    t = pd.date_range(INICIO, periods=n, freq="1min", tz="UTC")
    return tabela([{"abertura_em": t[i], "abertura": a[i], "maxima": max(a[i], f[i]) + folga[i], "minima": min(a[i], f[i]) - folga[i], "fechamento": f[i],
                    "volume": vol[i], "volume_cotacao": vol[i] * f[i], "volume_comprador": vol[i] / 2, "negocios": 10,
                    "recebido_em": t[i] + timedelta(minutes=1, seconds=2), "origem": "teste"} for i in range(n)])


def modelo(direcao=1):
    return {"tecnicas": [TECNICA], "pesos": [0.0], "intercepto": 3.0 * direcao, "corte": 0.01, "ate": "2026-07-31 23:54:00+00:00",
            "estrategia": "x", "evidencia": {"operacoes": 500, "acerto": 0.6, "r_bruto": 0.3, "r_por_bps": 0.01}}


def montar(tmp_path, estrategias=(("expiracao_fixa", 5, 5),), ativo="ETHUSDT", com_eventos=True, especialistas=None, usar_cache=True):
    dados = tmp_path / "dados"
    raiz = dados / "mercado"
    v = velas()
    ArmazemVelas(raiz).gravar(ativo, v, AGORA)
    config = {"modo": "paper", "banca": 100, "risco_por_operacao": 1, "min_operacoes_evidencia": 200, "limites": LIMITES,
              "mercados": [{"mercado": "cripto", "ativos": [ativo], "modalidades": [
                  {"tipo": t, "candle": c, "expiracao": x, "payout": 0.85} if t == "expiracao_fixa" else
                  {"tipo": t, "candle": c, "expiracao": x, "custo_bps": 20, "stop_atr": 1.5, "alvo_atr": 3, "vende": False} for t, c, x in estrategias]}]}
    (dados / "operacao.json").write_text(json.dumps(config), encoding="utf-8")
    pasta_motor = dados / "modelos" / "motor"
    pasta_motor.mkdir(parents=True)
    for t, c, x in estrategias:
        (pasta_motor / f"{ativo}_{t}_{c}m_{x}m.json").write_text(json.dumps(modelo()), encoding="utf-8")
    Diario(dados / "operacao" / "diario.db")  # cria o diário como o motor faz
    eventos = ArmazemEventos(raiz)
    if com_eventos:
        gravar_eventos(eventos, ativo)
    coord = Coordenador(raiz, Quadro(dados / "quadro" / "quadro.db"), dados / "operacao" / "diario.db", dados / "operacao.json", pasta_motor,
                        dados / "modelos", relogio=lambda: AGORA + timedelta(seconds=20), usar_cache=usar_cache, especialistas=especialistas)
    # Os cenários não devem depender do espaço usado no computador que roda a suíte.
    # O teste de disco cheio define um limite próprio e continua cobrindo essa proteção.
    coord.quadro.limite_disco = 1.0
    return coord, dados, v


def gravar_eventos(eventos: ArmazemEventos, ativo: str, ate: datetime = AGORA) -> None:
    g = np.random.default_rng(1)
    t0 = ate - timedelta(minutes=60)
    trades = [{"agg_id": i, "preco": 100 + g.normal(), "quantidade": abs(g.normal()) + 0.1, "comprador_agressor": bool(i % 3), "ocorrido_em": t0 + timedelta(seconds=10 * i),
               "recebido_em": t0 + timedelta(seconds=10 * i + 1), "origem": "teste"} for i in range(360)]
    eventos.gravar("trades", ativo, trades[:180])
    eventos.gravar("trades", ativo, trades[180:])  # duas partes no mesmo dia, como a coleta faz
    livro = [{"update_id": i, "ocorrido_em": t0 + timedelta(seconds=30 * i), "recebido_em": t0 + timedelta(seconds=30 * i),
              "melhor_compra": 99.9, "melhor_venda": 100.1, "spread_bps": 2.0, "desequilibrio_5": 0.1 * (i % 5), "desequilibrio_20": 0.05,
              "profundidade_compra": 1000.0, "profundidade_venda": 900.0} for i in range(120)]
    eventos.gravar("livro", ativo, livro)
    eventos.gravar("funding", ativo, [{"ocorrido_em": ate - timedelta(hours=2), "recebido_em": ate - timedelta(hours=2), "funding": 0.0001}])
    vela = ate - timedelta(minutes=1)
    eventos.gravar("previsoes", ativo, [{"modelo": f"{ativo}-15m-teste", "horizonte": 15, "ocorrido_em": vela, "recebido_em": ate + timedelta(seconds=7),
                                         "prob_sobe_bruta": 0.58, "prob_sobe": 0.52, "direcao": 1}])
    eventos.gravar("calendario", "GLOBAL", [{"id": "cpi", "ocorrido_em": ate + timedelta(minutes=30), "recebido_em": ate - timedelta(days=1), "fonte": "teste",
                                             "moeda": "USD", "nome": "CPI", "impacto": "High", "previsao": 3.0, "anterior": 2.9},
                                            {"id": "tarde", "ocorrido_em": ate + timedelta(minutes=40), "recebido_em": ate + timedelta(minutes=5), "fonte": "teste",
                                             "moeda": "USD", "nome": "Chegou depois", "impacto": "High", "previsao": None, "anterior": None}])
