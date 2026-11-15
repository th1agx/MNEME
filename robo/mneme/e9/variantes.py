"""Variantes ao vivo contra o motor, só com o mercado depois do registro (prever, não reler o passado).

Registradas em 15/11/2026 (Vault, "E9 - variantes ao vivo"). Nada aqui decide ou opera: o placar diário compara cada
variante com o motor nas mesmas condições. A decisão sobre uma variante só sai quando a amostra atingir o mínimo da régua
v1, e a promoção é do dono.

    python -m mneme.e9.variantes   # grava dados/e9/variantes/placar.json
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import PASTA_DADOS
from ..dados.armazem import ArmazemVelas
from .confirmacao import _apostas
from .dossie import _noticia
from .placar import comparar, placar
from .regua import REGUAS, amostra_minima

REGISTRO = {
    "versao": "variantes_v1",
    "registrado_em": "2026-11-15T17:45:00+00:00",
    "ativos": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "XAUUSD"],
    "variantes": {
        "V1a": "aposta contra a última vela de 1 min, expiração de 5 min, uma por vez, em todos os ativos",
        "V1b": "V1a só quando o corpo da última vela é maior que o desvio dos corpos da hora anterior",
        "V2": "motor só nas estratégias de candle 5 e 15 min",
        "V3": "motor sem SOLUSDT expiração fixa 1m→5m",
        "V4": "motor sem as decisões em que a notícia vigente é contra a direção",
    },
    "referencia": "decisões do motor (operadas e em sombra) de expiração fixa, com os preços de entrada e saída apurados",
    "payout_principal": 0.85,
    "decisao": "só quando cada variante tiver a amostra mínima da régua v1 (família de 5); antes disso o placar é acompanhamento",
    "promocao": "do dono",
}
DESDE = pd.Timestamp(REGISTRO["registrado_em"])
EXPIRACAO_V1 = 5


def decisoes_motor(diario: Path | str, desde: pd.Timestamp, ate: pd.Timestamp | None = None) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{diario}?mode=ro", uri=True, timeout=5)
    try:
        d = pd.read_sql_query("SELECT ativo, estrategia, vela, direcao, tipo, contexto, preco_entrada, preco_saida FROM decisoes "
                              "WHERE situacao = 'encerrada' AND modalidade = 'expiracao_fixa'", con)
    finally:
        con.close()
    if d.empty:
        return d
    d["tempo"] = pd.to_datetime(d["vela"], utc=True, format="ISO8601")
    d = d[(d["tempo"] >= desde) & ((d["tempo"] < ate) if ate is not None else True)].copy()
    d["candle"] = d["estrategia"].str.split("|").str[2].str.rstrip("m").astype(int)
    d["noticia"] = [_noticia(json.loads(c), int(x)) for c, x in zip(d["contexto"], d["direcao"])]
    d["retorno"] = d["preco_saida"] / d["preco_entrada"] - 1
    d["direcao"] = d["direcao"].astype(float)
    # A chave junta ativo e estratégia: várias estratégias podem decidir a mesma vela.
    d["chave"] = d["ativo"]
    d["ativo"] = d["ativo"] + "|" + d["estrategia"].str.split("|", n=1).str[1]
    return d[["ativo", "chave", "estrategia", "tempo", "direcao", "retorno", "candle", "noticia", "tipo"]].reset_index(drop=True)


def filtrar_motor(m: pd.DataFrame, variante: str) -> pd.DataFrame:
    if variante == "V2":
        return m[m["candle"].isin([5, 15])]
    if variante == "V3":
        return m[m["estrategia"] != "SOLUSDT|expiracao_fixa|1m|5m"]
    if variante == "V4":
        return m[m["noticia"] != "contra"]
    raise ValueError(variante)


def apostas_reversao(v: pd.DataFrame, ativo: str, desde: pd.Timestamp, forte: bool, expiracao: int = EXPIRACAO_V1) -> pd.DataFrame:
    """Contra a última vela fechada de 1 min. A versão forte exige um corpo maior que o desvio dos corpos da hora anterior."""
    corpo = v["fechamento"] - v["abertura"]
    direcao = -np.sign(corpo)
    ok = (direcao != 0) & (v.index >= desde)
    if forte:
        ok &= corpo.abs() > corpo.shift(1).rolling(60, min_periods=60).std()
    tempos = v.index[ok.to_numpy()]
    return _apostas(v, ativo, tempos, direcao[ok].to_numpy(), expiracao)


def placar_do_dia(diario: Path | str, armazem: ArmazemVelas, ativos=tuple(REGISTRO["ativos"]), desde: pd.Timestamp = DESDE,
                  ate: pd.Timestamp | None = None) -> dict:
    ate = ate or pd.Timestamp(datetime.now(timezone.utc))
    payout = REGISTRO["payout_principal"]
    saida = {"desde": desde.isoformat(), "ate": ate.isoformat(), "amostra_minima_por_variante": amostra_minima(REGUAS["v1"], payout, familia=5)}
    motor = decisoes_motor(diario, desde, ate)
    saida["motor"] = placar(motor) if not motor.empty else {"apostas": 0}
    for variante in ("V2", "V3", "V4"):
        f = filtrar_motor(motor, variante) if not motor.empty else motor
        saida[variante] = {**(placar(f) if not f.empty else {"apostas": 0}),
                           "pareado_contra_motor": comparar(f, motor, payout) if not motor.empty else None}
    for variante, forte in (("V1a", False), ("V1b", True)):
        partes = []
        for ativo in ativos:
            v = armazem.ler(ativo, inicio=(desde - pd.Timedelta(hours=2)).to_pydatetime(), como_de=ate.to_pydatetime())
            if len(v) > 70:
                partes.append(apostas_reversao(v, ativo, desde, forte))
        todas = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["ativo", "tempo", "direcao", "retorno"])
        saida[variante] = {**(placar(todas) if len(todas) else {"apostas": 0}),
                           "por_ativo": {a: placar(g)["expectativa"][payout] for a, g in todas.groupby("ativo")} if len(todas) else {}}
    return saida


def main() -> None:
    dados = Path(os.getenv("MNEME_DADOS", str(PASTA_DADOS)))
    raiz = Path(os.getenv("MNEME_DADOS_MERCADO", str(dados / "mercado")))
    destino = dados / "e9" / "variantes"
    destino.mkdir(parents=True, exist_ok=True)
    p = placar_do_dia(dados / "operacao" / "diario.db", ArmazemVelas(raiz))
    (destino / "placar.json").write_text(json.dumps({"registro": REGISTRO, **p}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: (v.get("apostas") if isinstance(v, dict) else v) for k, v in p.items()}, default=str))


if __name__ == "__main__":
    main()
