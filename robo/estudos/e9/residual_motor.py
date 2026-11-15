"""O motor tem vantagem própria ou só exposição ao mercado? Prepara a entrada do `residual-edge-analyzer`.

Declarado antes de ver o resultado (Vault, "E9 - vantagem residual do motor", 15/11/2026):
- estratégia: retorno diário da política do motor nas estratégias que ele OPERA hoje, apostando 1% da banca por aposta;
- referência principal ("viés de alta"): sempre CALL nas mesmas apostas;
- sensibilidade: seguir a última vela de 1 min nas mesmas apostas; e o retorno diário do próprio ativo (média dos ativos);
- regime: volatilidade do dia anterior em tercis dos 30 dias anteriores (só o passado);
- histórico de 2024-11-01 a 2026-08-01 (sem a área selada), dentro da amostra dos pesos do motor;
- ao vivo: as operadas do diário, à parte.

Uso: python residual_motor.py <pasta_mercado> <pasta_modelos_motor> <diario.db> <estrategias_operadas.txt> <pasta_saida>
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.e9.confirmacao import apostas_motor
from mneme.e9.placar import pnl_digital
from mneme.laboratorio.confluencia import ATRASO, grade_de_sinais
from mneme.laboratorio.horizontes import continuas

INICIO, FIM = pd.Timestamp("2024-11-01", tz="UTC"), pd.Timestamp("2026-08-01", tz="UTC")
PAYOUT, APOSTA = 0.85, 0.01


def regime_diario(v: pd.DataFrame) -> pd.Series:
    """Tercil da volatilidade do dia anterior entre os 30 dias anteriores: nada do próprio dia entra."""
    r = np.log(v["fechamento"]).diff()
    vol = r.groupby(r.index.floor("D")).std().shift(1)
    lo, hi = vol.rolling(30).quantile(1 / 3), vol.rolling(30).quantile(2 / 3)
    return pd.Series(np.where(vol.isna() | lo.isna(), None, np.where(vol <= lo, "vol_baixa", np.where(vol >= hi, "vol_alta", "vol_media"))), index=vol.index)


def ultima_vela(v: pd.DataFrame, tempos: pd.DatetimeIndex) -> np.ndarray:
    c = continuas(v)
    return np.sign((c["fechamento"] - c["abertura"]).reindex(tempos).to_numpy())


def serie(apostas: pd.DataFrame, coluna: str) -> pd.Series:
    pnl = pnl_digital(apostas[coluna].to_numpy(), apostas["retorno"].to_numpy(), PAYOUT) * APOSTA
    return pd.Series(pnl, index=pd.DatetimeIndex(apostas["tempo"])).groupby(lambda t: t.floor("D")).sum()


def main() -> None:
    raiz, pasta_motor, diario, lista, saida = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
    saida.mkdir(parents=True, exist_ok=True)
    operadas = [l.strip() for l in lista.read_text().splitlines() if l.strip()]
    armazem = ArmazemVelas(raiz)
    velas, partes, mercado, regimes = {}, [], {}, {}
    for estrategia in operadas:
        ativo, _, candle, expiracao = estrategia.split("|")
        candle, expiracao = int(candle.rstrip("m")), int(expiracao.rstrip("m"))
        if ativo not in velas:
            velas[ativo] = armazem.ler(ativo, inicio=INICIO.to_pydatetime(), fim=FIM.to_pydatetime())
            dia = velas[ativo]["fechamento"].groupby(velas[ativo].index.floor("D"))
            mercado[ativo] = dia.last().pct_change()
            regimes[ativo] = regime_diario(velas[ativo])
        modelo = json.loads((pasta_motor / f"{estrategia.replace('|', '_')}.json").read_text(encoding="utf-8"))
        sinais = grade_de_sinais(velas[ativo], candle)
        a = apostas_motor(velas[ativo], modelo, ativo, candle, expiracao, INICIO, FIM, sinais)
        a["call"] = 1.0
        a["momento"] = ultima_vela(velas[ativo], pd.DatetimeIndex(a["tempo"]))
        a["estrategia"] = estrategia
        partes.append(a)
        print(estrategia, len(a), flush=True)
    todas = pd.concat(partes, ignore_index=True)
    tabela = pd.DataFrame({"strategy_return": serie(todas, "direcao"), "always_call_return": serie(todas, "call"),
                           "momentum_return": serie(todas, "momento")})
    tabela["market_return"] = pd.concat(mercado, axis=1).mean(axis=1).reindex(tabela.index)
    tabela["volatility_regime"] = pd.concat(regimes, axis=1).mode(axis=1)[0].reindex(tabela.index)
    tabela = tabela.dropna()
    tabela.index = tabela.index.strftime("%Y-%m-%d")
    tabela.rename_axis("date").to_csv(saida / "historico.csv")
    # Ao vivo: operadas do diário, apostando 1% por aposta (pnl já está em unidades por aposta x tamanho).
    con = sqlite3.connect(f"file:{diario}?mode=ro", uri=True)
    vivo = pd.read_sql("SELECT vela, pnl, tamanho FROM decisoes WHERE tipo = 'operada' AND situacao = 'encerrada' AND modalidade = 'expiracao_fixa'", con)
    vivo["dia"] = pd.to_datetime(vivo["vela"], utc=True, format="ISO8601").dt.strftime("%Y-%m-%d")
    (vivo.assign(r=vivo["pnl"] / vivo["tamanho"] * APOSTA).groupby("dia")["r"].sum().rename("strategy_return")
     .rename_axis("date").to_csv(saida / "ao_vivo.csv"))
    print("dias historico", len(tabela), "dias ao vivo", vivo["dia"].nunique(), "apostas historico", len(todas), flush=True)


if __name__ == "__main__":
    main()
