"""Quanto do começo da janela de velas ainda muda o sinal das técnicas?

Calcula a grade de sinais com a janela do motor e com começos mais tardios, e mede a partir de quantas velas depois do
começo as linhas ficam idênticas. Se ficam idênticas bem antes do fim da janela, o quadro pode usar uma janela menor
sem mudar nenhum sinal. Uso: python estudos/quadro/janela_tecnicas.py [pasta_mercado]
"""

from __future__ import annotations

import sys
import time

import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.laboratorio.confluencia import grade_de_sinais
from mneme.motor.ciclo import DIAS_DE_JANELA

raiz = sys.argv[1] if len(sys.argv) > 1 else "dados/mercado"
velas = ArmazemVelas(raiz)
for ativo in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
    fim = pd.Timestamp(velas.ultima_abertura(ativo))
    for candle in (1, 5, 15):
        dias = DIAS_DE_JANELA[candle]
        v = velas.ler(ativo, inicio=(fim - pd.Timedelta(days=2 * dias)).to_pydatetime())
        t = time.monotonic()
        ref = grade_de_sinais(v, candle)
        custo = time.monotonic() - t
        piores = []
        for fracao in (0.25, 0.5, 0.75, 1.0):
            comeco = v.index[0] + pd.Timedelta(days=dias * fracao)
            g = grade_de_sinais(v[v.index >= comeco], candle)
            diferentes = (g != ref.loc[g.index]).any(axis=1)
            ultima = diferentes[diferentes].index.max() if diferentes.any() else None
            piores.append(round(((ultima - comeco) / pd.Timedelta(days=1)) if ultima is not None else 0.0, 3))
        print(f"{ativo} {candle}min janela_motor={dias}d custo={custo:.2f}s ultima_diferenca_em_dias_apos_o_comeco={piores}", flush=True)
