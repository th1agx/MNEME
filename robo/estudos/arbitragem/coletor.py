"""Coletor de livro (melhor compra e melhor venda) em 4 mercados, só de leitura, para medir arbitragem de verdade.

Binance à vista, Binance perpétuo, Bybit à vista e OKX à vista, para BTC, ETH e SOL. A cada segundo grava a última
cotação de cada mercado e a hora em que ela chegou, num Parquet por hora. Sem chave, sem ordem.

    python coletor.py      # roda até ser parado; o systemd reinicia se cair
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pandas as pd
import websockets

SAIDA = Path(os.getenv("ARBITRAGEM_SAIDA", "/home/ubuntu/lab/arbitragem")) / "livro"
ATIVOS = ("BTC", "ETH", "SOL")
ultimo: dict[tuple[str, str], tuple[float, float, float, float, float]] = {}  # (mercado, ativo) -> (compra, qtd, venda, qtd, chegou_em)


async def binance(url: str, mercado: str) -> None:
    fluxos = "/".join(f"{a.lower()}usdt@bookTicker" for a in ATIVOS)
    async for ws in websockets.connect(f"{url}/stream?streams={fluxos}", ping_interval=20):
        try:
            async for msg in ws:
                d = json.loads(msg)["data"]
                ultimo[(mercado, d["s"][:-4])] = (float(d["b"]), float(d["B"]), float(d["a"]), float(d["A"]), time.time())
        except websockets.ConnectionClosed:
            continue


async def bybit() -> None:
    async for ws in websockets.connect("wss://stream.bybit.com/v5/public/spot", ping_interval=20):
        try:
            await ws.send(json.dumps({"op": "subscribe", "args": [f"orderbook.1.{a}USDT" for a in ATIVOS]}))
            async for msg in ws:
                d = json.loads(msg)
                if "data" in d and d["data"].get("b") and d["data"].get("a"):
                    b, a = d["data"]["b"][0], d["data"]["a"][0]
                    ultimo[("bybit", d["data"]["s"][:-4])] = (float(b[0]), float(b[1]), float(a[0]), float(a[1]), time.time())
        except websockets.ConnectionClosed:
            continue


async def okx() -> None:
    async for ws in websockets.connect("wss://ws.okx.com:8443/ws/v5/public", ping_interval=20):
        try:
            await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "bbo-tbt", "instId": f"{a}-USDT"} for a in ATIVOS]}))
            async for msg in ws:
                d = json.loads(msg)
                if d.get("data"):
                    x = d["data"][0]
                    ultimo[("okx", d["arg"]["instId"].split("-")[0])] = (float(x["bids"][0][0]), float(x["bids"][0][1]), float(x["asks"][0][0]),
                                                                       float(x["asks"][0][1]), time.time())
        except websockets.ConnectionClosed:
            continue


async def gravar() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas, hora = [], None
    while True:
        await asyncio.sleep(1 - time.time() % 1)
        agora = time.time()
        for (mercado, ativo), (c, qc, v, qv, chegou) in list(ultimo.items()):
            linhas.append((agora, mercado, ativo, c, qc, v, qv, agora - chegou))
        atual = time.strftime("%Y%m%d-%H", time.gmtime(agora))
        if hora is None:
            hora = atual
        if atual != hora and linhas:
            df = pd.DataFrame(linhas, columns=["t", "mercado", "ativo", "compra", "qtd_compra", "venda", "qtd_venda", "idade_s"])
            df.to_parquet(SAIDA / f"{hora}.parquet")
            (SAIDA / "batimento").write_text(str(agora))
            linhas, hora = [], atual


async def main() -> None:
    await asyncio.gather(binance("wss://stream.binance.com:9443", "binance"), binance("wss://fstream.binance.com", "binance_perp"), bybit(), okx(), gravar())


if __name__ == "__main__":
    asyncio.run(main())
