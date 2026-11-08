"""A1 do E9 v2: o dossiê das operações. Uma linha por decisão encerrada (operada e sombra), com tudo o que se sabia no momento.

Só leitura: o diário é aberto em modo de leitura, e as velas são lidas como de cada momento (a mesma regra do quadro F1).
Os atributos de regime aqui são os mais simples e causais (volatilidade e tendência da última hora). Os regimes do R1 e o
fluxo de ordens do O1 entram depois como colunas novas.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from ..dados.armazem import ArmazemVelas
from ..motor.conhecimento import _sentimento

JANELA_VOL = 60  # minutos da volatilidade e da tendência
DIAS_REFERENCIA = 7  # a volatilidade é comparada com a dos 7 dias anteriores, só do passado


def _ler_decisoes(diario: Path) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{diario}?mode=ro", uri=True, timeout=5)
    try:
        return pd.read_sql_query("SELECT chave, estrategia, mercado, ativo, modalidade, vela, decidido_em, latencia_s, direcao, forca, expectativa, "
                                 "evidencia, motivos_recusa, contexto, sinal, tipo, tamanho, resultado, pnl, encerrado_por FROM decisoes "
                                 "WHERE situacao = 'encerrada' ORDER BY vela, chave", con)
    finally:
        con.close()


def _noticia(contexto: list[dict], direcao: int) -> str:
    if not any(c.get("tipo") == "noticia" for c in contexto):
        return "sem notícia"
    s = _sentimento(contexto)
    return "neutra" if s == 0 else "a favor" if s == direcao else "contra"


def _regime(armazem: ArmazemVelas, ativo: str, momentos: pd.Series) -> pd.DataFrame:
    """Volatilidade (desvio dos retornos de 1 min) e tendência da última hora, e o percentil da volatilidade nos 7 dias anteriores.

    Tudo calculado com as velas que já tinham chegado em cada momento: nenhuma vela recebida depois entra.
    """
    vazio = pd.DataFrame({"vol_60": np.nan, "vol_pct_7d": np.nan, "tendencia_60": np.nan}, index=momentos.index)
    if momentos.empty:
        return vazio
    inicio = (momentos.min() - pd.Timedelta(days=DIAS_REFERENCIA + 1)).to_pydatetime()
    v = armazem.ler(ativo, inicio=inicio, como_de=momentos.max().to_pydatetime())
    if v.empty:
        return vazio
    retorno = np.log(v["fechamento"]).diff()
    vol = retorno.rolling(JANELA_VOL, min_periods=JANELA_VOL).std()
    tendencia = np.log(v["fechamento"]).diff(JANELA_VOL) / (vol * np.sqrt(JANELA_VOL))
    # Uma vela só conta para o momento se já estava fechada e recebida nele.
    disponivel = (v.index + pd.Timedelta(minutes=1)).to_series(index=v.index)
    if "recebido_em" in v:
        disponivel = pd.concat([disponivel, v["recebido_em"].fillna(disponivel)], axis=1).max(axis=1)
    serie = pd.DataFrame({"vol": vol, "tendencia": tendencia, "disponivel": disponivel}).dropna(subset=["vol"])
    saida = vazio.copy()
    for i, momento in momentos.items():
        conhecido = serie[serie["disponivel"] <= momento]
        if conhecido.empty:
            continue
        atual = conhecido.iloc[-1]
        passado = conhecido.loc[conhecido.index >= conhecido.index[-1] - pd.Timedelta(days=DIAS_REFERENCIA), "vol"]
        saida.loc[i] = [atual["vol"], float((passado <= atual["vol"]).mean()), atual["tendencia"]]
    return saida.astype(float)


def montar_dossie(diario: Path | str, armazem: ArmazemVelas) -> pd.DataFrame:
    d = _ler_decisoes(Path(diario))
    if d.empty:
        return d
    partes = d["estrategia"].str.split("|", expand=True)
    d["candle"] = partes[2].str.rstrip("m").astype(int)
    d["horizonte"] = partes[3].str.rstrip("m").astype(int)
    d["vela"] = pd.to_datetime(d["vela"], utc=True, format="ISO8601")
    d["decidido_em"] = pd.to_datetime(d["decidido_em"], utc=True, format="ISO8601")
    sinal = d["sinal"].map(json.loads)
    contexto = d["contexto"].map(json.loads)
    evidencia = d["evidencia"].map(json.loads)
    recusas = d["motivos_recusa"].map(json.loads)
    d["acao"] = sinal.map(lambda s: s.get("acao"))
    d["payout"] = sinal.map(lambda s: s.get("payout"))
    d["empate"] = sinal.map(lambda s: s.get("empate"))
    d["recusada"] = recusas.map(bool)
    d["motivo_recusa"] = recusas.map(lambda r: "; ".join(r) if r else "")
    d["acerto_treino"] = evidencia.map(lambda e: e.get("acerto"))
    d["noticia"] = [_noticia(c, int(x)) for c, x in zip(contexto, d["direcao"])]
    d["trechos_conhecimento"] = contexto.map(lambda c: sum(1 for x in c if x.get("tipo") == "conhecimento"))
    d["ganho"] = d["resultado"].map({"ganho": 1.0, "perda": 0.0})
    d["pnl_por_unidade"] = d["pnl"] / d["tamanho"].replace(0, np.nan)
    d["hora_utc"] = d["vela"].dt.hour
    d["faixa_hora"] = (d["hora_utc"] // 4 * 4).map(lambda h: f"{h:02d}-{h + 4:02d}h")
    d["dia_semana"] = d["vela"].dt.day_of_week
    d["dia"] = d["vela"].dt.floor("D")
    regimes = [_regime(armazem, ativo, grupo["decidido_em"]) for ativo, grupo in d.groupby("ativo")]
    d = d.join(pd.concat(regimes))
    d["vol_quintil"] = _quintil(d["vol_pct_7d"])
    # R1: regime do momento, só com o passado. Tendência pelo retorno da última hora medido em desvios (|z| ≥ 1),
    # volatilidade pelo terço em que cai nos 7 dias anteriores.
    d["tendencia"] = np.where(d["tendencia_60"].isna(), None,
                              np.where(d["tendencia_60"] >= 1, "alta", np.where(d["tendencia_60"] <= -1, "baixa", "lateral")))
    vol = np.where(d["vol_pct_7d"] < 1 / 3, "vol baixa", np.where(d["vol_pct_7d"] > 2 / 3, "vol alta", "vol media"))
    d["regime"] = [None if t is None or np.isnan(p) else f"{v}-{t}" for v, t, p in zip(vol, d["tendencia"], d["vol_pct_7d"])]
    # Rótulo descritivo para recortar o passado: usa a distribuição do período todo. Um filtro por força que vire hipótese
    # precisa de limites calculados só com o passado, no executor.
    d["forca_quintil"] = _quintil(d.groupby("estrategia")["forca"].rank(pct=True))
    return d.drop(columns=["sinal", "contexto", "evidencia", "motivos_recusa"])


def _quintil(p: pd.Series) -> pd.Series:
    """Faixa de 1 a 5 a partir de um percentil; sem valor, fica vazio."""
    return pd.Series(np.where(p.isna(), np.nan, np.clip(np.ceil(p * 5), 1, 5)), index=p.index)
