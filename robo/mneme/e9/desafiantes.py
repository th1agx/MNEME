"""Desafiantes do ETH 1m/5m: filtros sobre as próprias decisões do motor, medidos só depois do registro.

Registrados em 16/11/2026, junto com a confirmação C2 (`estudos/e9/registro_c2_eth_1m5m.json`). Nenhum muda o motor nem a C2:
cada um é um subconjunto das decisões que o motor já toma, e o placar compara o subconjunto com a estratégia inteira. A
decisão sobre um desafiante sai com a amostra fixada no registro, e a promoção é do dono.

    python -m mneme.e9.desafiantes   # grava dados/e9/desafiantes/placar.json
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import PASTA_DADOS

BRASILIA = timezone(timedelta(hours=-3))
BASE = "ETHUSDT|expiracao_fixa|1m|5m"
PARES = ("BTCUSDT|expiracao_fixa|1m|5m", "SOLUSDT|expiracao_fixa|1m|5m")
REGISTRO = {
    "versao": "desafiantes_eth_v1",
    "registrado_em": "2026-11-16T23:40:00+00:00",
    "base": BASE,
    "desafiantes": {
        "D1": "sem entradas das 18h à meia-noite de Brasília (faixa pior nas três criptos no período exploratório de 06 a 16/11)",
        "D2": "só decisões com força >= 0,0617, a mediana da força do ETH 1m/5m de 06 a 16/11 (fixada sem olhar resultado)",
        "D3": "só quando BTC e SOL 1m/5m decidiram a mesma vela na mesma direção",
    },
    "medida": "acerto em sinais apurados (empate fora), intervalo por sorteio de blocos de dia, e a diferença para a base no mesmo período",
    "empate": 1 / 1.85,
    "amostra_minima": "cada desafiante precisa do próprio n para separar 56% de 54,05%: 4.027 sinais independentes vezes o efeito de desenho; "
                      "como cada um vê só parte da base, leva mais tempo que a C2. Antes disso o placar é acompanhamento.",
    "familia": "3 desafiantes: o limite de baixo da decisão usa alfa 0,05/3",
    "promocao": "do dono",
}
DESDE = pd.Timestamp(REGISTRO["registrado_em"])
FORCA_D2 = 0.0617
SORTEIOS = 5000


def ler_decisoes(diario: Path | str, desde: pd.Timestamp = DESDE) -> pd.DataFrame:
    """Decisões CALL/PUT das três estratégias de 1m/5m com entrada depois do registro."""
    con = sqlite3.connect(f"file:{diario}?mode=ro", uri=True, timeout=5)
    try:
        d = pd.read_sql_query(
            "SELECT estrategia, vela, forca, json_extract(sinal, '$.acao') AS acao, json_extract(sinal, '$.entrada_em') AS entrada, resultado "
            f"FROM decisoes WHERE estrategia IN ({','.join('?' * (1 + len(PARES)))}) AND json_extract(sinal, '$.acao') IN ('CALL', 'PUT')",
            con, params=(BASE, *PARES))
    finally:
        con.close()
    d["entrada"] = pd.to_datetime(d["entrada"], utc=True, format="ISO8601")
    d["vela"] = pd.to_datetime(d["vela"], utc=True, format="ISO8601")
    return d[d["entrada"] > desde].reset_index(drop=True)


def selecionar(d: pd.DataFrame, nome: str) -> pd.DataFrame:
    """As decisões da base que cada desafiante aceita (todas, inclusive as ainda sem resultado)."""
    base = d[d["estrategia"] == BASE]
    if nome == "base":
        return base
    if nome == "D1":
        return base[base["entrada"].dt.tz_convert(BRASILIA).dt.hour < 18]
    if nome == "D2":
        return base[base["forca"] >= FORCA_D2]
    if nome == "D3":
        outros = [set(zip(d.loc[d["estrategia"] == p, "vela"], d.loc[d["estrategia"] == p, "acao"])) for p in PARES]
        ok = [all((v, a) in o for o in outros) for v, a in zip(base["vela"], base["acao"])]
        return base[np.asarray(ok, dtype=bool)] if len(base) else base
    raise ValueError(nome)


def placar(sel: pd.DataFrame, semente: int = 7) -> dict:
    a = sel[sel["resultado"].isin(["ganho", "perda"])]
    if a.empty:
        return {"sinais": 0, "empates": int((sel["resultado"] == "empate").sum())}
    g = (a["resultado"] == "ganho").astype(int)
    dia = a["entrada"].dt.tz_convert(BRASILIA).dt.date
    por = g.groupby(dia).agg(["sum", "count"])
    r = np.random.default_rng(semente).integers(0, len(por), (SORTEIOS, len(por)))
    s = por["sum"].to_numpy()[r].sum(1) / por["count"].to_numpy()[r].sum(1)
    return {"sinais": int(len(a)), "acerto": float(g.mean()), "dias": int(len(por)), "empates": int((sel["resultado"] == "empate").sum()),
            "limite_baixo_95": float(np.quantile(s, 0.05)), "limite_baixo_familia": float(np.quantile(s, 0.05 / 3)),
            "intervalo_95": [float(np.quantile(s, 0.025)), float(np.quantile(s, 0.975))]}


def placar_geral(diario: Path | str, desde: pd.Timestamp = DESDE) -> dict:
    d = ler_decisoes(diario, desde)
    base = placar(selecionar(d, "base"))
    saida = {"base": base}
    for nome in ("D1", "D2", "D3"):
        p = placar(selecionar(d, nome))
        if p["sinais"] and base["sinais"]:
            p["diferenca_para_base"] = p["acerto"] - base["acerto"]
            p["fracao_da_base"] = p["sinais"] / base["sinais"]
        saida[nome] = p
    return saida


def main() -> None:
    dados = Path(os.getenv("MNEME_DADOS", str(PASTA_DADOS)))
    destino = dados / "e9" / "desafiantes"
    destino.mkdir(parents=True, exist_ok=True)
    p = placar_geral(dados / "operacao" / "diario.db")
    (destino / "placar.json").write_text(json.dumps({"registro": REGISTRO, "atualizado_em": datetime.now(timezone.utc).isoformat(), **p},
                                                    ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v.get("sinais") for k, v in p.items()}))


if __name__ == "__main__":
    main()
