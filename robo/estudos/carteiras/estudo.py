"""Inteligência de carteiras em Solana: o que as operações dos traders medidos dizem sobre o mercado. Só leitura.

Usa as operações que o robô de traders já grava (provedor de sinais, sem identificar a fonte) e preços públicos de
1 minuto por pool (GeckoTerminal, sem chave). Não é copy trading: o resultado vira informação para a inteligência central.

Mede:
- rentabilidade líquida, drawdown e consistência por trader (operações encerradas, com custo de DEX);
- antecedência: o preço anda depois da compra? Comparado com momentos sorteados no mesmo token (placebo);
- acumulação e distribuição: fluxo líquido de compras dos traders contra o retorno da hora seguinte;
- coordenação: pares de traders que compram o mesmo token juntos mais do que o acaso explicaria.

    python estudo.py precos --tokens 40
    python estudo.py analisar
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.request
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

BANCO = Path(os.getenv("MNEME_BANCO", "/home/ubuntu/mneme/robo/dados/mneme.db"))
SAIDA = Path(os.getenv("CARTEIRAS_SAIDA", "/home/ubuntu/lab/carteiras"))
CUSTO_IDA_VOLTA = 2 * (0.001 + 0.005)  # o mesmo do simulado do robô: 0,1% de taxa e 0,5% de slippage em cada ponta
HORIZONTES = (5, 15, 60)
JANELA_JUNTOS_MIN = 5
SEMENTE = 0


def _get(url: str):
    for tentativa in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "mneme-estudo", "Accept": "application/json"}), timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(4 + tentativa * 6)  # limite público de ~30 chamadas por minuto
    return None


def operacoes() -> pd.DataFrame:
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    o = pd.read_sql_query("SELECT trader_id, lado, token, simbolo, valor_usd, quando FROM operacoes_traders WHERE rede = 'solana'", con)
    o["quando"] = pd.to_datetime(o["quando"], utc=True, format="ISO8601")
    return o.sort_values("quando")


def precos(tokens: int) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    o = operacoes()
    inicio = int(o["quando"].min().timestamp()) - 3600
    for token in o["token"].value_counts().index[:tokens]:
        arquivo = SAIDA / f"preco_{token}.parquet"
        if arquivo.exists():
            continue
        pools = _get(f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{token}/pools?page=1")
        if not pools or not pools.get("data"):
            continue
        pool = pools["data"][0]["attributes"]["address"]  # o pool de maior liquidez vem primeiro
        linhas, antes = [], int(time.time())
        while antes > inicio:
            d = _get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/minute?aggregate=1&limit=1000&before_timestamp={antes}&token=base")
            lista = (d or {}).get("data", {}).get("attributes", {}).get("ohlcv_list", [])
            if not lista:
                break
            linhas += lista
            antes = int(lista[-1][0]) - 60
            time.sleep(2.2)
        if linhas:
            p = pd.DataFrame(linhas, columns=["t", "abertura", "maxima", "minima", "fechamento", "volume"]).drop_duplicates("t")
            p.index = pd.to_datetime(p["t"], unit="s", utc=True)
            p.sort_index().drop(columns="t").to_parquet(arquivo)
            print(json.dumps({"token": token, "pool": pool, "minutos": len(p)}), flush=True)


def _preco_em(p: pd.Series, t: pd.Timestamp) -> float:
    """Último fechamento até o instante (nada do futuro). Minutos sem negócio repetem o anterior."""
    anterior = p.loc[:t]
    return float(anterior.iloc[-1]) if len(anterior) and (t - anterior.index[-1]) <= pd.Timedelta(minutes=10) else float("nan")


def _antecedencia(eventos: pd.DataFrame, precos_: dict[str, pd.Series], rng) -> pd.DataFrame:
    linhas = []
    for e in eventos.itertuples():
        p = precos_.get(e.token)
        if p is None:
            continue
        t0 = e.quando.floor("min")
        agora = _preco_em(p, t0)
        if not agora or np.isnan(agora):
            continue
        linha = {"trader_id": e.trader_id, "token": e.token, "lado": e.lado, "quando": t0,
                 "antes_60": np.log(agora / _preco_em(p, t0 - pd.Timedelta(minutes=60)))}
        for h in HORIZONTES:
            linha[f"depois_{h}"] = np.log(_preco_em(p, t0 + pd.Timedelta(minutes=h)) / agora)
        # Placebo: um minuto sorteado no mesmo token e no mesmo período, para separar o trader da tendência do token.
        sorteado = p.index[rng.integers(0, max(len(p) - 61, 1))]
        base = _preco_em(p, sorteado)
        for h in HORIZONTES:
            linha[f"placebo_{h}"] = np.log(_preco_em(p, sorteado + pd.Timedelta(minutes=h)) / base) if base else np.nan
        linhas.append(linha)
    return pd.DataFrame(linhas)


def _resultado_traders() -> pd.DataFrame:
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    r = pd.read_sql_query("SELECT trader_id, retorno_pct, aberta_em, fechada_em FROM resultados_traders WHERE rede = 'solana'", con)
    r["liquido"] = r["retorno_pct"] / 100 - CUSTO_IDA_VOLTA
    r["fechada_em"] = pd.to_datetime(r["fechada_em"], utc=True, format="ISO8601")
    linhas = []
    for trader, g in r.sort_values("fechada_em").groupby("trader_id"):
        curva = g["liquido"].cumsum()
        dias = g.groupby(g["fechada_em"].dt.date)["liquido"].sum()
        linhas.append({"trader_id": trader, "encerradas": len(g), "acerto_bruto": float((g["retorno_pct"] > 0).mean()),
                       "acerto_liquido": float((g["liquido"] > 0).mean()), "liquido_medio_pct": float(g["liquido"].mean() * 100),
                       "liquido_total_pct": float(g["liquido"].sum() * 100), "drawdown_pct": float((curva - curva.cummax()).min() * 100),
                       "dias_positivos_pct": float((dias > 0).mean() * 100), "dias": int(len(dias))})
    return pd.DataFrame(linhas)


def _coordenacao(o: pd.DataFrame, rng, sorteios: int = 200) -> dict:
    """Pares de traders que compram o mesmo token em até 5 min. Compara com o mesmo cálculo depois de embaralhar os horários dentro de cada token."""
    compras = o[o["lado"] == "buy"][["trader_id", "token", "quando"]]

    def pares(c: pd.DataFrame) -> Counter:
        cont = Counter()
        for _, g in c.groupby("token"):
            g = g.sort_values("quando")
            ts, ids = g["quando"].to_numpy(), g["trader_id"].to_numpy()
            for i in range(len(g)):
                j = i + 1
                while j < len(g) and ts[j] - ts[i] <= np.timedelta64(JANELA_JUNTOS_MIN, "m"):
                    if ids[i] != ids[j]:
                        cont[tuple(sorted((ids[i], ids[j])))] += 1
                    j += 1
        return cont

    real = pares(compras)
    repetidos_real = sum(1 for v in real.values() if v >= 3)
    nulos = []
    for _ in range(sorteios):
        emb = compras.copy()
        emb["quando"] = emb.groupby("token")["quando"].transform(lambda s: s.sample(frac=1, random_state=int(rng.integers(1e9))).to_numpy())
        nulos.append(sum(1 for v in pares(emb).values() if v >= 3))
    nulos = np.array(nulos)
    return {"pares_que_compraram_juntos_3x_ou_mais": repetidos_real, "esperado_pelo_acaso": float(nulos.mean()), "p_valor": float((nulos >= repetidos_real).mean()),
            "maiores": [{"pares": list(k), "vezes": v} for k, v in real.most_common(5)]}


def analisar() -> None:
    rng = np.random.default_rng(SEMENTE)
    o = operacoes()
    precos_ = {a.stem.removeprefix("preco_"): pd.read_parquet(a)["fechamento"] for a in SAIDA.glob("preco_*.parquet")}
    traders = _resultado_traders()
    medidos = traders[traders["encerradas"] >= 5]
    e = _antecedencia(o[o["token"].isin(precos_)], precos_, rng)
    saida = {"periodo": [str(o["quando"].min()), str(o["quando"].max())], "operacoes_solana": len(o), "traders": int(o["trader_id"].nunique()),
             "tokens_com_preco": len(precos_), "eventos_com_preco": len(e), "custo_ida_volta_pct": CUSTO_IDA_VOLTA * 100,
             "traders_com_5_ou_mais_encerradas": len(medidos),
             "rentabilidade": {"liquido_medio_pct_mediana": float(medidos["liquido_medio_pct"].median()) if len(medidos) else None,
                               "fracao_com_liquido_positivo": float((medidos["liquido_total_pct"] > 0).mean()) if len(medidos) else None,
                               "drawdown_mediano_pct": float(medidos["drawdown_pct"].median()) if len(medidos) else None}}
    antecedencia = {}
    for lado in ("buy", "sell"):
        g = e[e["lado"] == lado]
        for h in HORIZONTES:
            dif = (g[f"depois_{h}"] - g[f"placebo_{h}"]).dropna()
            antecedencia[f"{lado}_{h}min"] = {"eventos": int(len(dif)), "retorno_medio_bps": float(g[f"depois_{h}"].mean() * 1e4),
                                             "placebo_medio_bps": float(g[f"placebo_{h}"].mean() * 1e4), "diferenca_bps": float(dif.mean() * 1e4),
                                             "erro_padrao_bps": float(dif.std() / np.sqrt(max(len(dif), 1)) * 1e4),
                                             "fracao_subiu": float((g[f"depois_{h}"] > 0).mean())}
        antecedencia[f"{lado}_antes_60min_bps"] = float(g["antes_60"].mean() * 1e4)
    saida["antecedencia"] = antecedencia
    # Acumulação: fluxo líquido (compras menos vendas, em US$) por token e hora contra o retorno da hora seguinte.
    o2 = o[o["token"].isin(precos_)].copy()
    o2["hora"] = o2["quando"].dt.floor("h")
    o2["fluxo"] = np.where(o2["lado"] == "buy", 1, -1) * o2["valor_usd"].abs().fillna(0)
    fluxo = o2.groupby(["token", "hora"])["fluxo"].sum().reset_index()
    fluxo["seguinte"] = [np.log(_preco_em(precos_[r.token], r.hora + pd.Timedelta(hours=2)) / _preco_em(precos_[r.token], r.hora + pd.Timedelta(hours=1)))
                         for r in fluxo.itertuples()]
    fluxo = fluxo.dropna()
    from scipy.stats import spearmanr
    saida["acumulacao"] = {"horas_token": len(fluxo), "spearman_fluxo_retorno_seguinte": float(spearmanr(fluxo["fluxo"], fluxo["seguinte"]).statistic) if len(fluxo) > 10 else None}
    saida["coordenacao"] = _coordenacao(o, rng)
    SAIDA.mkdir(parents=True, exist_ok=True)
    traders.to_csv(SAIDA / "traders.csv", index=False)
    (SAIDA / "analise.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(saida, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("etapa", choices=["precos", "analisar"])
    p.add_argument("--tokens", type=int, default=40)
    a = p.parse_args()
    precos(a.tokens) if a.etapa == "precos" else analisar()
