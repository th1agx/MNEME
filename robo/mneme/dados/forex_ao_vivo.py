"""Moedas e ouro ao vivo, de graça e sem chave, para o motor prever Forex e ouro (em sombra enquanto a evidência não paga).

- Moedas (EUR/USD, GBP/USD, USD/JPY, USD/CAD): velas de 1 minuto do gráfico público do Yahoo. Sem volume nessa fonte.
- Ouro: o XAU/USD não tem fonte gratuita em tempo real; usa o PAXG da Binance (token lastreado em ouro) como aproximação,
  marcado em `origem` como "binance:PAXGUSDT" e só no horário do mercado de ouro.
- Só entra vela fechada. A primeira versão de cada vela fica (o armazém não reescreve). Uma fonte que falha não para as outras.

    python -m mneme.dados.forex_ao_vivo
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

from ..config import PASTA_DADOS
from .armazem import ArmazemVelas, agora_utc
from .binance import FonteBinance
from .velas import linha, tabela

log = logging.getLogger("mneme.forex")
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}"
MOEDAS = {"EURUSD": "EURUSD=X", "EURGBP": "EURGBP=X", "USDJPY": "USDJPY=X", "EURJPY": "EURJPY=X",
          "GBPUSD": "GBPUSD=X", "USDCAD": "USDCAD=X"}
OURO, PROXY_OURO = "XAUUSD", "PAXGUSDT"
JANELA = timedelta(minutes=30)
SEGUNDO_DO_CICLO = 8


def velas_yahoo(resposta: dict, agora: datetime) -> pd.DataFrame:
    """Converte a resposta do gráfico em velas no formato do armazém. Vela ainda aberta ou sem fechamento fica de fora."""
    r = resposta["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    linhas = []
    for i, ts in enumerate(r.get("timestamp") or []):
        o, h, low, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, low, c) or ts % 60 or ts + 60 > agora.timestamp():
            continue
        linhas.append(linha(ts * 1000, o, max(h, o, c), min(low, o, c), c, 0.0, 0.0, 0, 0.0, agora, "yahoo"))
    return tabela(linhas)


def ouro_aberto(t: datetime) -> bool:
    """Ouro à vista: de domingo 23:00 a sexta 22:00 UTC, com pausa diária das 22:00 às 23:00 UTC (horário de inverno dos EUA)."""
    dia, hora = t.weekday(), t.hour
    if dia == 5 or (dia == 6 and hora < 23) or (dia == 4 and hora >= 22):
        return False
    return hora != 22


class ColetorForex:
    def __init__(self, armazem: ArmazemVelas, cliente: httpx.Client | None = None, binance=None, relogio=agora_utc, pasta: Path | None = None):
        self.armazem = armazem
        self.cliente = cliente or httpx.Client(timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        self.binance = binance or FonteBinance()
        self.relogio = relogio
        self.batimento = Path(pasta or armazem.raiz) / "forex.batimento"

    def _moeda(self, par: str, simbolo: str, agora: datetime) -> int:
        inicio = int((agora - JANELA).timestamp())
        r = self.cliente.get(YAHOO.format(simbolo=simbolo), params={"interval": "1m", "period1": inicio, "period2": int(agora.timestamp())})
        r.raise_for_status()
        v = velas_yahoo(r.json(), agora)
        return self.armazem.gravar(par, v, agora) if not v.empty else 0

    def _ouro(self, agora: datetime) -> int:
        v = self.binance.recentes(PROXY_OURO, agora - JANELA, agora)
        if v.empty:
            return 0
        v = v[[ouro_aberto(t.to_pydatetime()) for t in pd.to_datetime(v["abertura_em"], utc=True)]].copy()
        v["origem"] = f"binance:{PROXY_OURO}"
        return self.armazem.gravar(OURO, tabela(v.to_dict("records")), agora) if not v.empty else 0

    def ciclo(self) -> dict:
        agora = self.relogio()
        resumo = {}
        for par, simbolo in MOEDAS.items():
            try:
                resumo[par] = self._moeda(par, simbolo, agora)
            except Exception as erro:  # uma fonte fora do ar não para as outras
                resumo[par] = f"falhou: {type(erro).__name__}"
        try:
            resumo[OURO] = self._ouro(agora) if ouro_aberto(agora) else 0
        except Exception as erro:
            resumo[OURO] = f"falhou: {type(erro).__name__}"
        self.batimento.parent.mkdir(parents=True, exist_ok=True)  # com o mercado fechado nada é gravado, e a pasta pode não existir
        self.batimento.write_text(json.dumps({"quando": agora.isoformat(), "resumo": resumo}), encoding="utf-8")
        return resumo


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    raiz = os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado"))
    coletor = ColetorForex(ArmazemVelas(raiz))
    while True:
        time.sleep((SEGUNDO_DO_CICLO - time.time() % 60) % 60 or 60)
        log.info(json.dumps(coletor.ciclo(), ensure_ascii=False))


if __name__ == "__main__":
    main()
