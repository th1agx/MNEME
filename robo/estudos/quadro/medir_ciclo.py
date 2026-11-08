"""Mede o ciclo real do quadro na A1, no mesmo ritmo do serviço, sem gravar no banco de produção.

Uso (dentro do contêiner do quadro, com MNEME_QUADRO numa pasta temporária):
    python medir_ciclo.py [minutos]
Imprime o tempo de aquecimento, o de cada ciclo, a média, o pior minuto e o pico de memória do processo.
"""

from __future__ import annotations

import json
import resource
import sys
import time

import numpy as np
import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.metodologias import _escala, perfil_de_volume
from mneme.quadro.__main__ import DESLOCAMENTO_S, montar


def laco(v, atr, janela=96, faixas=24):
    tipico = ((v["maxima"] + v["minima"] + v["fechamento"]) / 3).to_numpy()
    volume, f = v["volume"].to_numpy(), v["fechamento"].to_numpy()
    poc, dentro = np.full(len(v), np.nan), np.full(len(v), np.nan)
    for t in range(janela - 1, len(v)):
        precos, pesos = tipico[t - janela + 1:t + 1], volume[t - janela + 1:t + 1]
        if np.isnan(precos).any() or pesos.sum() == 0:
            continue
        hist, bordas = np.histogram(precos, faixas, weights=pesos)
        meios = (bordas[:-1] + bordas[1:]) / 2
        poc[t] = meios[int(hist.argmax())]
        ordem = np.argsort(hist)[::-1]
        escolhidas = ordem[:int(np.searchsorted(np.cumsum(hist[ordem]), 0.7 * hist.sum())) + 1]
        dentro[t] = float(meios[escolhidas].min() <= f[t] <= meios[escolhidas].max())
    return pd.DataFrame({"vp_dist_poc": (v["fechamento"] - poc) / _escala(atr), "vp_na_area_valor": dentro}, index=v.index)


def conferir_perfil(raiz: str) -> None:
    velas = ArmazemVelas(raiz)
    for ativo in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        v = velas.ler(ativo, inicio=(pd.Timestamp(velas.ultima_abertura(ativo)) - pd.Timedelta(days=4)).to_pydatetime())
        atr = (v["maxima"] - v["minima"]).rolling(14).mean()
        for regra in ("1min", "5min", "15min"):
            r = v.resample(regra, label="left", closed="left").agg({"abertura": "first", "maxima": "max", "minima": "min",
                                                                   "fechamento": "last", "volume": "sum"}) if regra != "1min" else v
            a = atr.reindex(r.index)
            assert perfil_de_volume(r, a).equals(laco(r, a)), (ativo, regra)
    print("perfil vetorizado igual ao laco nos dados reais", flush=True)


def main() -> None:
    minutos = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    coord, _ = montar()
    conferir_perfil(str(coord.raiz))
    t = time.monotonic()
    coord.aquecer()
    print(json.dumps({"aquecer_s": round(time.monotonic() - t, 2)}), flush=True)
    tempos = []
    for _ in range(minutos):
        time.sleep((DESLOCAMENTO_S - time.time() % 60) % 60 or 60)
        t = time.monotonic()
        r = coord.ciclo()
        r["apuradas"] = coord.apurar()
        r["segundos"] = round(time.monotonic() - t, 2)
        tempos.append(r["segundos"])
        print(json.dumps(r), flush=True)
    pedidos = coord.quadro.con.execute("SELECT especialista, situacao, COUNT(*), ROUND(AVG(segundos), 3), ROUND(MAX(segundos), 3) "
                                       "FROM pedidos GROUP BY especialista, situacao").fetchall()
    print(json.dumps({"media_s": round(float(np.mean(tempos)), 2), "pior_s": max(tempos),
                      "pico_ram_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
                      "pedidos": [tuple(p) for p in pedidos]}), flush=True)


if __name__ == "__main__":
    main()
