"""Plataformas de opções digitais (IQ Option, Quotex): nomes dos ativos e regras, sempre com a origem.

Nada aqui é suposto como fato. Expirações, regra de empate e payout só valem como "observados" quando vêm das operações
registradas na conta demo (`captura`). Até lá, são desconhecidos e o simulador marca o resultado como aproximação.
Não há API oficial em nenhuma das duas; a Quotex proíbe automação nas regras oficiais, e a IQ Option tem stop order da
CVM. O Motor 02 só estuda, gera sinais e mede.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PLATAFORMAS = {"iqoption": "IQ Option", "quotex": "Quotex"}

# Ativo da plataforma → série de referência no armazém do MNEME (Binance para cripto, Dukascopy para moedas e ouro).
REFERENCIA = {"EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "XAUUSD": "XAUUSD",
              "BTCUSD": "BTCUSDT", "BTCUSDT": "BTCUSDT", "ETHUSD": "ETHUSDT", "ETHUSDT": "ETHUSDT", "SOLUSD": "SOLUSDT", "SOLUSDT": "SOLUSDT"}


@dataclass(frozen=True)
class Ativo:
    simbolo: str  # sem barra e sem sufixo, em maiúsculas: EURUSD
    otc: bool  # OTC: preço sintético da própria plataforma, fora do horário do mercado real; não tem referência externa

    @property
    def referencia(self) -> str | None:
        return None if self.otc else REFERENCIA.get(self.simbolo)


def ler_ativo(texto: str) -> Ativo:
    """Aceita como a plataforma escreve: "EUR/USD", "EUR/USD (OTC)", "eurusd-otc", "BTC/USD"."""
    t = texto.strip().upper()
    otc = bool(re.search(r"\bOTC\b", t))
    simbolo = re.sub(r"[^A-Z]", "", re.sub(r"\bOTC\b", "", t))
    if not simbolo:
        raise ValueError(f"ativo vazio: {texto!r}")
    return Ativo(simbolo, otc)


def plataforma(texto: str) -> str:
    chave = re.sub(r"[^a-z]", "", texto.strip().lower())
    if chave not in PLATAFORMAS:
        raise ValueError(f"plataforma desconhecida: {texto!r} (use {', '.join(PLATAFORMAS)})")
    return chave
