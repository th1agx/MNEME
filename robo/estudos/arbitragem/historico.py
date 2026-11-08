"""Estudo de arbitragem com velas públicas de 1 minuto. Só leitura: nenhuma ordem, nenhuma chave.

Mede, para BTC, ETH e SOL:
- diferença instantânea entre corretoras (Binance, Bybit, OKX, MEXC), com o custo das duas pontas;
- quanto tempo uma diferença dura (o que importa para a latência da A1);
- arbitragem estatística: a diferença volta à média? Em quanto tempo? Paga 4 pontas de taxa?
- diferenças persistentes (prêmio de uma corretora sobre outra);
- base entre o à vista e o perpétuo da Binance, e o funding (carry), que tem horizonte de horas.

Limite: vela de 1 minuto usa o último negócio, não a melhor compra e venda, e os fechamentos não são simultâneos. Isso
superestima as oportunidades; o coletor ao vivo (`coletor.py`) mede o livro de verdade.

    python historico.py baixar --dias 30
    python historico.py analisar
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

SAIDA = Path(os.getenv("ARBITRAGEM_SAIDA", "/home/ubuntu/lab/arbitragem"))
ATIVOS = ("BTC", "ETH", "SOL")
# Taxa de tomador por ponta, tabela pública de conta comum, sem desconto de token ou de volume.
TAXA = {"binance": 0.0010, "bybit": 0.0010, "okx": 0.0010, "mexc": 0.0005, "binance_perp": 0.0005}


def _get(url: str):
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "mneme-estudo"}), timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1 + tentativa * 2)
    raise RuntimeError(f"falhou: {url.split('?')[0]}")


def _quadro(linhas, ms, fechamento) -> pd.Series:
    s = pd.Series({pd.Timestamp(int(l[ms]), unit="ms", tz="UTC"): float(l[fechamento]) for l in linhas})
    return s.sort_index()


def baixar(dias: int) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    fim = int(time.time() // 60 * 60 * 1000)
    inicio = fim - dias * 86_400_000
    for ativo in ATIVOS:
        sim = f"{ativo}USDT"
        series = {}
        for nome, url, passo, ms, fe in (
            ("binance", f"https://api.binance.com/api/v3/klines?symbol={sim}&interval=1m&limit=1000&startTime={{a}}", 1000, 0, 4),
            ("binance_perp", f"https://fapi.binance.com/fapi/v1/klines?symbol={sim}&interval=1m&limit=1500&startTime={{a}}", 1500, 0, 4),
            ("mexc", f"https://api.mexc.com/api/v3/klines?symbol={sim}&interval=1m&limit=1000&startTime={{a}}", 1000, 0, 4)):
            partes, a = [], inicio
            while a < fim:
                lote = _get(url.format(a=a))
                if not lote:
                    break
                partes += lote
                a = int(lote[-1][0]) + 60_000
            series[nome] = _quadro(partes, ms, fe)
        partes, b = [], fim  # Bybit devolve do mais novo para o mais velho
        while b > inicio:
            lote = _get(f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sim}&interval=1&limit=1000&end={b}")["result"]["list"]
            if not lote:
                break
            partes += lote
            b = int(lote[-1][0]) - 60_000
        series["bybit"] = _quadro(partes, 0, 4)
        partes, depois = [], fim  # OKX: 100 velas por chamada, paginando para trás
        while depois > inicio:
            lote = _get(f"https://www.okx.com/api/v5/market/history-candles?instId={ativo}-USDT&bar=1m&limit=100&after={depois}")["data"]
            if not lote:
                break
            partes += lote
            depois = int(lote[-1][0])
            time.sleep(0.12)
        series["okx"] = _quadro(partes, 0, 4)
        quadro = pd.DataFrame(series)
        quadro = quadro[quadro.index >= pd.Timestamp(inicio, unit="ms", tz="UTC")]
        quadro.to_parquet(SAIDA / f"velas_{ativo}.parquet")
        funding = []
        a = inicio
        while a < fim:
            lote = _get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sim}&limit=1000&startTime={a}")
            if not lote:
                break
            funding += lote
            a = int(lote[-1]["fundingTime"]) + 1
        pd.DataFrame(funding).to_parquet(SAIDA / f"funding_{ativo}.parquet")
        print(json.dumps({"ativo": ativo, "minutos": len(quadro), "colunas": {c: int(quadro[c].notna().sum()) for c in quadro}, "funding": len(funding)}), flush=True)


def _corridas(marca: np.ndarray) -> np.ndarray:
    """Tamanho de cada sequência de minutos seguidos com a marca verdadeira."""
    if not marca.any():
        return np.array([], dtype=int)
    bordas = np.diff(np.r_[0, marca.astype(int), 0])
    return np.flatnonzero(bordas == -1) - np.flatnonzero(bordas == 1)


def _meia_vida(s: pd.Series) -> float:
    """Meia-vida (minutos) de um AR(1) na diferença; infinito se não volta à média."""
    x = s.dropna()
    phi = np.corrcoef(x.iloc[:-1], x.iloc[1:])[0, 1]
    return float(-np.log(2) / np.log(phi)) if 0 < phi < 1 else float("inf")


def _estatistica(s: pd.Series, custo_ida_volta: float, janela: int = 1440, entrada: float = 2.0) -> dict:
    """Arbitragem estatística com z-score só do passado: abre em |z| > 2, fecha quando o z cruza o zero. Uma posição por vez."""
    media = s.rolling(janela, min_periods=janela // 2).mean().shift(1)
    desvio = s.rolling(janela, min_periods=janela // 2).std().shift(1)
    z = ((s - media) / desvio).to_numpy()
    valores = s.to_numpy()
    lucros, aberta, lado, preco = [], False, 0, 0.0
    for i in range(len(z)):
        if np.isnan(z[i]):
            continue
        if not aberta and abs(z[i]) > entrada:
            aberta, lado, preco = True, -np.sign(z[i]), valores[i]
        elif aberta and np.sign(z[i]) != -lado:
            lucros.append(lado * (valores[i] - preco))
            aberta = False
    lucros = np.array(lucros)
    return {"operacoes": int(len(lucros)), "bruto_medio_bps": float(lucros.mean() * 1e4) if len(lucros) else float("nan"),
            "liquido_medio_bps": float((lucros.mean() - custo_ida_volta) * 1e4) if len(lucros) else float("nan"),
            "acerto_liquido": float((lucros > custo_ida_volta).mean()) if len(lucros) else float("nan")}


def analisar() -> None:
    relatorio = []
    for ativo in ATIVOS:
        q = pd.read_parquet(SAIDA / f"velas_{ativo}.parquet")
        base = q["binance"]
        for outra in ("bybit", "okx", "mexc"):
            s = np.log(q[outra] / base).dropna()
            custo = TAXA["binance"] + TAXA[outra]  # duas pontas, ao mesmo tempo
            acima = (s.abs() > custo).to_numpy()
            corridas = _corridas(acima)
            relatorio.append({"tipo": "entre corretoras", "ativo": ativo, "par": f"{outra} x binance", "minutos": int(len(s)),
                              "diferenca_media_bps": float(s.mean() * 1e4), "desvio_bps": float(s.std() * 1e4),
                              "p99_abs_bps": float(s.abs().quantile(0.99) * 1e4), "custo_bps": custo * 1e4,
                              "minutos_acima_do_custo_pct": float(acima.mean() * 100), "duracao_max_min": int(corridas.max()) if len(corridas) else 0,
                              "corridas_de_3min_ou_mais": int((corridas >= 3).sum()), "meia_vida_min": _meia_vida(s),
                              "estatistica": _estatistica(s, 2 * custo)})
        b = np.log(q["binance_perp"] / base).dropna()
        f = pd.read_parquet(SAIDA / f"funding_{ativo}.parquet")
        taxa = f["fundingRate"].astype(float)
        dias = (b.index[-1] - b.index[0]).total_seconds() / 86400
        carry = float(taxa.sum())  # vendido no perpétuo e comprado no à vista: recebe o funding positivo
        custo_carry = 2 * (TAXA["binance"] + TAXA["binance_perp"])  # entra e sai nas duas pernas
        relatorio.append({"tipo": "à vista x perpétuo", "ativo": ativo, "minutos": int(len(b)), "base_media_bps": float(b.mean() * 1e4),
                          "base_desvio_bps": float(b.std() * 1e4), "meia_vida_base_min": _meia_vida(b), "funding_periodos": int(len(taxa)),
                          "funding_positivo_pct": float((taxa > 0).mean() * 100), "carry_no_periodo_pct": carry * 100,
                          "carry_anual_bruto_pct": carry * 365 / dias * 100, "custo_entrada_saida_pct": custo_carry * 100,
                          "carry_liquido_no_periodo_pct": (carry - custo_carry) * 100, "dias": dias,
                          "estatistica_base": _estatistica(b, 2 * (TAXA["binance"] + TAXA["binance_perp"]))})
    (SAIDA / "analise.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1, default=float))
    for r in relatorio:
        print(json.dumps(r, ensure_ascii=False, default=float))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("etapa", choices=["baixar", "analisar"])
    p.add_argument("--dias", type=int, default=30)
    a = p.parse_args()
    baixar(a.dias) if a.etapa == "baixar" else analisar()
