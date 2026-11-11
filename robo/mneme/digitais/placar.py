"""Placar do Motor 02 por nível de fidelidade. Cada número diz de onde veio; nenhum se passa por outro.

- `registrado-demo`: operações feitas por uma pessoa na conta demo, com o preço, o payout e o lucro da plataforma.
- `calibrado`: simulado com a divergência medida na conciliação. Só existe com conciliação suficiente (mínimo abaixo).
- `aproximacao-referencia`: o simulado do motor com preço da Binance e payout hipotético (85%).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from .captura import regras_observadas
from .conciliacao import resumo as resumo_conciliacao

MINIMO_PARA_CALIBRAR = 200


def _medidas(lucros_por_aposta: list[float], resultados: list[str], payouts: list[float]) -> dict:
    decididas = [r for r in resultados if r != "empate"]
    acerto = float(np.mean([r == "ganho" for r in decididas])) if decididas else None
    payout = float(np.median(payouts)) if payouts else None
    return {"operacoes": len(resultados), "empates": resultados.count("empate"), "acerto": acerto, "payout_mediano": payout,
            "empate_necessario": 1 / (1 + payout) if payout else None,
            "resultado_medio_por_aposta": float(np.mean(lucros_por_aposta)) if lucros_por_aposta else None}


def placar(con: sqlite3.Connection, diario: Path | str | None = None, payout_hipotese: float = 0.85) -> dict:
    saida: dict = {"registrado-demo": {}, "calibrado": {}, "aproximacao-referencia": None, "regras_observadas": regras_observadas(con),
                   "conciliacao": resumo_conciliacao(con)}
    for (plat,) in con.execute("SELECT DISTINCT plataforma FROM operacoes_demo"):
        ops = con.execute("SELECT * FROM operacoes_demo WHERE plataforma = ?", (plat,)).fetchall()
        todos = _medidas([o["lucro"] / o["valor"] for o in ops], [o["resultado"] for o in ops], [o["payout"] for o in ops if o["payout"]])
        do_mneme = [o for o in ops if o["sinal_chave"]]
        todos["so_sinais_do_mneme"] = _medidas([o["lucro"] / o["valor"] for o in do_mneme], [o["resultado"] for o in do_mneme],
                                               [o["payout"] for o in do_mneme if o["payout"]]) if do_mneme else None
        saida["registrado-demo"][plat] = todos
        conciliadas = saida["conciliacao"].get(plat, {}).get("conciliadas", 0)
        saida["calibrado"][plat] = (f"disponível com {conciliadas} conciliadas" if conciliadas >= MINIMO_PARA_CALIBRAR
                                    else f"indisponível: {conciliadas} de {MINIMO_PARA_CALIBRAR} operações conciliadas")
    if diario and Path(diario).exists():
        d = sqlite3.connect(f"file:{diario}?mode=ro", uri=True)
        linhas = d.execute("""SELECT resultado FROM decisoes WHERE modalidade = 'expiracao_fixa' AND resultado IS NOT NULL
                              AND (motivos_recusa IS NULL OR motivos_recusa IN ('', '[]'))""").fetchall()
        d.close()
        resultados = [l[0] for l in linhas]
        ganhos = resultados.count("ganho")
        perdas = resultados.count("perda")
        aprox = _medidas([payout_hipotese if r == "ganho" else -1.0 if r == "perda" else 0.0 for r in resultados], resultados, [payout_hipotese])
        aprox["fonte"] = "motor no simulado: preço da Binance e payout hipotético"
        for plat, m in saida["registrado-demo"].items():
            if m["payout_mediano"] and ganhos + perdas:
                aprox[f"expectativa_com_payout_observado_{plat}"] = (ganhos * m["payout_mediano"] - perdas) / (ganhos + perdas)
        saida["aproximacao-referencia"] = aprox
    return saida
