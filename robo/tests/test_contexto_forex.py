"""Contexto determinístico para os pares Forex: histórico e agenda conhecidos no instante da decisão."""

import pandas as pd

from mneme.dados.forex_ao_vivo import MOEDAS
from mneme.forex import eventos_altos_relevantes, moedas_do_par


def test_pares_monitorados_expoem_as_duas_moedas_da_agenda():
    assert {"EURUSD", "EURGBP", "USDJPY", "EURJPY"}.issubset(MOEDAS)
    assert moedas_do_par("EURUSD") == ("EUR", "USD")
    assert moedas_do_par("EURGBP") == ("EUR", "GBP")
    assert moedas_do_par("USDJPY") == ("USD", "JPY")
    assert moedas_do_par("EURJPY") == ("EUR", "JPY")


def test_evento_alto_so_bloqueia_se_ja_era_conhecido_e_afeta_o_par():
    agora = pd.Timestamp("2026-11-18T13:00:00Z")
    agenda = pd.DataFrame([
        {"nome": "CPI US", "moeda": "USD", "impacto": "High", "ocorrido_em": agora + pd.Timedelta(minutes=20), "recebido_em": agora - pd.Timedelta(minutes=5)},
        {"nome": "GDP Japão", "moeda": "JPY", "impacto": "High", "ocorrido_em": agora + pd.Timedelta(minutes=20), "recebido_em": agora - pd.Timedelta(minutes=5)},
        {"nome": "CPI futuro", "moeda": "USD", "impacto": "High", "ocorrido_em": agora + pd.Timedelta(minutes=10), "recebido_em": agora + pd.Timedelta(minutes=1)},
        {"nome": "Evento médio", "moeda": "EUR", "impacto": "Medium", "ocorrido_em": agora + pd.Timedelta(minutes=10), "recebido_em": agora - pd.Timedelta(minutes=1)},
    ])

    bloqueios = eventos_altos_relevantes(agenda, "EURUSD", agora, 30)

    assert bloqueios["nome"].tolist() == ["CPI US"]
