"""Roda o mapa de previsibilidade (mapa_v1) e grava o resultado. Uso: python estudos/e9/rodar_mapa.py <pasta_mercado> <saida.json>"""

import json
import sys
import time

import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.e9.mapa import PROTOCOLO, medir_celula, preparar

raiz, destino = sys.argv[1], sys.argv[2]
armazem = ArmazemVelas(raiz)
resultados = []
for ativo in PROTOCOLO["ativos"]:
    v = armazem.ler(ativo, inicio=pd.Timestamp(PROTOCOLO["inicio"], tz="UTC").to_pydatetime(),
                    fim=pd.Timestamp(PROTOCOLO["fim_desenvolvimento"], tz="UTC").to_pydatetime())
    for h in PROTOCOLO["horizontes"]:
        x, y = preparar(v, h)
        for alvo in PROTOCOLO["alvos"]:
            t = time.monotonic()
            r = medir_celula(x, y, alvo, h)
            if r is None:
                continue
            r |= {"ativo": ativo, "segundos": round(time.monotonic() - t, 1)}
            resultados.append(r)
            print(json.dumps(r, default=float), flush=True)
            with open(destino, "w") as saida:
                json.dump({"protocolo": PROTOCOLO, "resultados": resultados}, saida, default=float, indent=1)
