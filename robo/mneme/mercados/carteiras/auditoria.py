"""Auditoria do histórico de carteiras. Só leitura do banco; o resultado vai para o registro do laboratório e, de lá, ao Vault.

Mede qualidade dos dados, desempenho por carteira (com custo de DEX, placebo por sorteio e correção BH) e o timing das
compras contra minutos sorteados no mesmo token. Dados suspeitos são marcados por regra, nunca apagados do banco.

    python -m mneme.mercados.carteiras.auditoria --precos ~/lab/carteiras
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from ...config import PASTA_DADOS
from ...laboratorio.registro import Registro

CUSTO_IDA_VOLTA = 0.012  # 0,1% de taxa + 0,5% de slippage por ponta: o mesmo do simulado e do estudo de 08/11/2026
# Retorno acima de +1.000% numa posição de minutos ou horas é preço corrompido, não operação: em 08/11 houve um de +468.663%.
LIMITE_SUSPEITO_PCT = 1000.0
MINIMO_POSICOES = 5
SEMENTE = 0


def carregar(banco: Path | str) -> tuple[pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        ops = pd.read_sql("SELECT * FROM operacoes_traders", con)
        res = pd.read_sql("SELECT * FROM resultados_traders", con)
    finally:
        con.close()
    for df, colunas in ((ops, ("quando", "recebido_em")), (res, ("aberta_em", "fechada_em"))):
        for c in colunas:
            df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601")
    return ops, res


def impressao(ops: pd.DataFrame, res: pd.DataFrame) -> str:
    """Identifica o conjunto exato analisado: qualquer operação a mais ou a menos muda a impressão."""
    texto = "|".join(sorted(ops["event_id"])) + "#" + "|".join(sorted(res["event_id"] + ":" + res["retorno_pct"].round(6).astype(str)))
    return hashlib.sha256(texto.encode()).hexdigest()[:16]


def marcar_suspeitos(res: pd.DataFrame) -> pd.DataFrame:
    res = res.copy()
    res["suspeito"] = (res["retorno_pct"] > LIMITE_SUSPEITO_PCT) | (res["retorno_pct"] < -100.0)
    return res


def qualidade(ops: pd.DataFrame, res: pd.DataFrame) -> dict:
    lat = (ops["recebido_em"] - ops["quando"]).dt.total_seconds()
    por_trader = ops.groupby("trader_id").size()
    compras = ops.loc[ops["lado"] == "buy", ["trader_id", "token"]].drop_duplicates()
    vendas = ops[ops["lado"] == "sell"].merge(compras, how="left", indicator=True)
    return {
        "operacoes": int(len(ops)), "duplicatas_mesmo_conteudo": int(ops.duplicated(["trader_id", "token", "lado", "quando", "valor_usd"]).sum()),
        "traders": int(ops["trader_id"].nunique()), "tokens": int(ops["token"].nunique()),
        "redes": {k: int(v) for k, v in ops["rede"].value_counts().items()},
        "periodo": [str(ops["quando"].min()), str(ops["quando"].max())],
        "dias": sorted(str(d.date()) for d in ops["quando"].dt.floor("D").unique()),
        "operacoes_por_trader": {"1": int((por_trader == 1).sum()), "2-4": int(por_trader.between(2, 4).sum()),
                                 "5-19": int(por_trader.between(5, 19).sum()), "20+": int((por_trader >= 20).sum())},
        "latencia_s_p50_p90_p99": [round(float(lat.quantile(q)), 1) for q in (0.5, 0.9, 0.99)] if len(lat) else [],
        "vendas_sem_compra_no_periodo": int(vendas["_merge"].eq("left_only").sum()),
        "posicoes_encerradas": int(len(res)), "suspeitos": res.loc[res["suspeito"], ["trader", "rede", "retorno_pct", "aberta_em"]].astype(str).to_dict("records"),
    }


def ranking(res: pd.DataFrame, custo: float = CUSTO_IDA_VOLTA, minimo: int = MINIMO_POSICOES, sorteios: int = 2000) -> dict:
    """Por carteira, com custo. Compara cada carteira com `n` posições sorteadas do conjunto todo e corrige por BH."""
    rng = np.random.default_rng(SEMENTE)
    validos = res[~res["suspeito"]].sort_values("fechada_em").copy()
    validos["liq"] = validos["retorno_pct"] / 100 - custo
    todos = validos["liq"].to_numpy()
    linhas = []
    for tid, g in validos.groupby("trader_id"):
        r = g["liq"].to_numpy()
        n = len(r)
        if n < minimo:
            continue
        curva = np.cumprod(1 + np.clip(r, -1, None))
        p = float(stats.ttest_1samp(r, 0, alternative="greater").pvalue) if r.std() > 0 else 1.0
        acaso = rng.choice(todos, size=(sorteios, n), replace=True).mean(axis=1)
        linhas.append({"trader": g["trader"].iloc[-1], "rede": g["rede"].iloc[-1], "n": n, "acerto": float((r > 0).mean()),
                       "media_pct": float(r.mean() * 100), "mediana_pct": float(np.median(r) * 100),
                       "pior_queda_pct": float((curva / np.maximum.accumulate(np.r_[1.0, curva])[1:] - 1).min() * 100),
                       "metades_pct": [float(r[: n // 2].mean() * 100), float(r[n // 2:].mean() * 100)], "p": p,
                       "percentil_contra_acaso": float((acaso < r.mean()).mean())})
    tabela = pd.DataFrame(linhas)
    if not tabela.empty:
        tabela["q_bh"] = stats.false_discovery_control(tabela["p"].to_numpy())
        tabela = tabela.sort_values("media_pct", ascending=False)
    geral = {"n": int(len(todos)), "acerto": float((todos > 0).mean()) if len(todos) else None,
             "media_pct": float(todos.mean() * 100) if len(todos) else None, "mediana_pct": float(np.median(todos) * 100) if len(todos) else None}
    return {"geral": geral, "carteiras_com_minimo": int(len(tabela)), "minimo_posicoes": minimo,
            "acima_p95_contra_acaso": int((tabela["percentil_contra_acaso"] > 0.95).sum()) if len(tabela) else 0,
            "esperado_por_acaso": round(0.05 * len(tabela), 1),
            "significativas_q10": int((tabela["q_bh"] < 0.10).sum()) if len(tabela) else 0,
            "duas_metades_positivas": int(tabela["metades_pct"].apply(lambda m: m[0] > 0 and m[1] > 0).sum()) if len(tabela) else 0,
            "tabela": tabela.to_dict("records")}


def timing(ops: pd.DataFrame, precos: dict[str, pd.Series], horizontes=(5, 15, 60, 240), alta_forte: float = 0.20) -> dict:
    """Compras contra minutos sorteados no mesmo token. Entrada 1 min depois da operação: ninguém compra no mesmo instante."""
    rng = np.random.default_rng(SEMENTE)
    tolerancia = pd.Timedelta(minutes=2)

    def preco(s: pd.Series, t: pd.Timestamp) -> float:
        k = s.index.searchsorted(t)
        return float(s.iloc[k]) if k < len(s) and s.index[k] - t <= tolerancia else np.nan

    eventos = []
    for _, o in ops[(ops["lado"] == "buy") & ops["token"].isin(list(precos))].iterrows():
        s = precos[o["token"]]
        t = o["quando"].floor("min")
        p0 = preco(s, t + pd.Timedelta(minutes=1))
        if np.isnan(p0) or len(s) < 400:
            continue
        ev = {"antes60": p0 / preco(s, t - pd.Timedelta(minutes=59)) - 1}
        for h in horizontes:
            ev[f"depois{h}"] = preco(s, t + pd.Timedelta(minutes=1 + h)) / p0 - 1
        k = int(rng.integers(60, len(s) - 241))
        ev["placebo_antes60"], ev["placebo_depois60"] = float(s.iloc[k] / s.iloc[k - 60] - 1), float(s.iloc[k + 60] / s.iloc[k] - 1)
        eventos.append(ev)
    e = pd.DataFrame(eventos)
    if e.empty:
        return {"compras_com_preco": 0}

    def resumo(x: pd.Series) -> dict:
        x = x.dropna()
        return {"n": int(len(x)), "mediana_pct": float(x.median() * 100) if len(x) else None, "subiu": float((x > 0).mean()) if len(x) else None}

    forte = e["antes60"] > alta_forte
    return {"compras_com_preco": int(len(e)), "tokens_com_preco": len(precos),
            "antes60": resumo(e["antes60"]), "placebo_antes60": resumo(e["placebo_antes60"]),
            **{f"depois{h}": resumo(e[f"depois{h}"]) for h in horizontes}, "placebo_depois60": resumo(e["placebo_depois60"]),
            "depois60_apos_alta_forte": resumo(e.loc[forte, "depois60"]), "depois60_sem_alta_forte": resumo(e.loc[~forte, "depois60"]),
            "fracao_apos_alta_forte": float(forte.mean()),
            "aviso": "compras do mesmo token e minuto não são independentes: a significância nominal superestima a evidência"}


def ler_precos(pasta: Path | str) -> dict[str, pd.Series]:
    return {a.stem.removeprefix("preco_"): pd.read_parquet(a)["fechamento"] for a in Path(pasta).glob("preco_*.parquet")}


def auditar(banco: Path | str, pasta_precos: Path | str | None, registro: Registro | None = None) -> dict:
    ops, res = carregar(banco)
    res = marcar_suspeitos(res)
    resultado = {"qualidade": qualidade(ops, res), "ranking": ranking(res),
                 "timing": timing(ops, ler_precos(pasta_precos)) if pasta_precos and Path(pasta_precos).exists() else {"compras_com_preco": 0},
                 "custo_ida_volta": CUSTO_IDA_VOLTA, "limite_suspeito_pct": LIMITE_SUSPEITO_PCT}
    r = resultado["ranking"]
    # Quantas carteiras passariam do percentil 95 só por sorte (limite de 95% da binomial): acima disso, há algo a investigar.
    limite_acaso = int(stats.binom.ppf(0.95, r["carteiras_com_minimo"], 0.05)) if r["carteiras_com_minimo"] else 0
    r["limite_do_acaso_95"] = limite_acaso
    sem_vantagem = r["significativas_q10"] == 0 and r["acima_p95_contra_acaso"] <= limite_acaso
    resultado["natureza"] = "resultado-negativo" if sem_vantagem else "resultado-em-validacao"
    resultado["conclusao"] = ("Nenhuma carteira se distingue do acaso com esta amostra; o histórico não sustenta ranking nem sinal."
                              if sem_vantagem else "Há carteiras acima do acaso: só hipótese, a confirmar com dados posteriores.")
    if registro is not None:
        resumo = {k: v for k, v in resultado.items() if k != "ranking"} | {"ranking": {k: v for k, v in r.items() if k != "tabela"} | {"melhores": r["tabela"][:5]}}
        registro.anotar("carteiras", "auditoria do histórico", {"custo_ida_volta": CUSTO_IDA_VOLTA, "minimo_posicoes": MINIMO_POSICOES,
                                                                "limite_suspeito_pct": LIMITE_SUSPEITO_PCT}, impressao(ops, res), resumo)
    return resultado


def main() -> None:
    p = argparse.ArgumentParser(prog="mneme.mercados.carteiras.auditoria")
    p.add_argument("--banco", default=os.getenv("MNEME_BANCO", str(PASTA_DADOS / "mneme.db")))
    p.add_argument("--precos", default=os.getenv("MNEME_CARTEIRAS_PRECOS"), help="pasta com preco_<token>.parquet (velas de 1 min)")
    p.add_argument("--saida", default=str(PASTA_DADOS / "laboratorio" / "carteiras_auditoria.json"))
    p.add_argument("--sem-registro", action="store_true")
    a = p.parse_args()
    registro = None if a.sem_registro else Registro(Path(a.saida).parent / "experimentos.jsonl")
    resultado = auditar(a.banco, a.precos, registro)
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.saida).write_text(json.dumps(resultado, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    r = resultado["ranking"]
    print(f"{resultado['qualidade']['operacoes']} operações · {r['carteiras_com_minimo']} carteiras com {r['minimo_posicoes']}+ posições · "
          f"acima do acaso: {r['acima_p95_contra_acaso']} (esperado {r['esperado_por_acaso']}) · significativas: {r['significativas_q10']} · {resultado['natureza']}")


if __name__ == "__main__":
    main()
