"""Regras determinísticas do contexto Forex.

O módulo só identifica as moedas de uma paridade e filtra eventos já conhecidos.
Ele não escolhe direção, não chama a LLM e não consulta a rede: o Motor decide se
a política de risco configurada transforma o evento em veto.
"""

from __future__ import annotations

import pandas as pd


PARES_MONITORADOS = ("EURUSD", "EURGBP", "USDJPY", "EURJPY")


def moedas_do_par(ativo: str) -> tuple[str, ...]:
    """Retorna base e cotação das paridades que o MNEME acompanha."""
    par = ativo.upper().replace("/", "")
    if par not in PARES_MONITORADOS:
        return ()
    return par[:3], par[3:]


def eventos_altos_relevantes(eventos: pd.DataFrame, ativo: str, agora: pd.Timestamp, janela_minutos: int) -> pd.DataFrame:
    """Eventos High que afetam a paridade e já eram conhecidos em ``agora``.

    A agenda contém ocorrências futuras; portanto o corte é pela hora de chegada,
    não pela hora do evento. A janela cobre antes e depois da divulgação.
    """
    if janela_minutos < 0:
        raise ValueError("janela_minutos não pode ser negativa")
    moedas = moedas_do_par(ativo)
    if eventos.empty or not moedas:
        return eventos.iloc[0:0].copy()
    obrigatorias = {"nome", "moeda", "impacto", "ocorrido_em", "recebido_em"}
    if not obrigatorias.issubset(eventos.columns):
        raise ValueError("agenda de calendário incompleta")
    e = eventos.copy()
    e["ocorrido_em"] = pd.to_datetime(e["ocorrido_em"], utc=True)
    e["recebido_em"] = pd.to_datetime(e["recebido_em"], utc=True)
    instante = pd.Timestamp(agora)
    limite = pd.Timedelta(minutes=janela_minutos)
    mascara = (
        e["impacto"].astype(str).str.casefold().eq("high")
        & e["moeda"].astype(str).str.upper().isin(moedas)
        & e["recebido_em"].notna()
        & (e["recebido_em"] <= instante)
        & (e["ocorrido_em"] >= instante - limite)
        & (e["ocorrido_em"] <= instante + limite)
    )
    return e.loc[mascara].sort_values("ocorrido_em").reset_index(drop=True)
