"""C1 em duas fases. Uso:
    python estudos/e9/rodar_c1.py explorar  <pasta_mercado> <pasta_modelos_motor> <pasta_saida>
    python estudos/e9/rodar_c1.py confirmar <pasta_mercado> <pasta_modelos_motor> <pasta_saida>

A exploração treina e escolhe só com dados até 2026-02-01 e congela os artefatos com impressão. A confirmação abre o lacre
(uma vez por protocolo), confere as impressões e mede tudo no bloco de 2026-02-01 a 2026-08-01.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from mneme.dados.armazem import ArmazemVelas
from mneme.e9.confirmacao import (CONFIRMACAO, EXPLORACAO_ATE, PROTOCOLO_C1, VARIANTES, apostas_candidato, apostas_motor, filtrar_variante,
                                  impressao_protocolo, lacrar, prever_risco, risco_fora_da_amostra, treinar_candidato)
from mneme.e9.placar import comparar, intervalo_por_blocos, placar, pnl_digital
from mneme.e9.regua import empate, holm
from mneme.laboratorio.confluencia import grade_de_sinais

ATIVOS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
INICIO = pd.Timestamp("2024-11-01", tz="UTC")
PAYOUT = PROTOCOLO_C1["payout_principal"]
EMPATE = empate(PAYOUT)


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]


def _guardar(objeto, caminho: Path) -> str:
    caminho.write_bytes(pickle.dumps(objeto))
    return _sha(caminho)


def _carregar(caminho: Path, sha: str):
    if _sha(caminho) != sha:
        raise RuntimeError(f"artefato alterado depois da exploração: {caminho}")
    return pickle.loads(caminho.read_bytes())


def estrategias_base(pasta_motor: Path) -> list[tuple[str, int, int, dict]]:
    saida = []
    for ativo in ATIVOS:
        for a in sorted(pasta_motor.glob(f"{ativo}_expiracao_fixa_*m_*m.json")):
            candle, expiracao = (int(p.rstrip("m")) for p in a.stem.split("_")[-2:])
            if expiracao in (5, 15):
                saida.append((ativo, candle, expiracao, json.loads(a.read_text(encoding="utf-8"))))
    return saida


def base_motor(velas: dict, sinais: dict, estrategias, inicio, fim) -> pd.DataFrame:
    partes = []
    for ativo, candle, expiracao, modelo in estrategias:
        a = apostas_motor(velas[ativo], modelo, ativo, candle, expiracao, inicio, fim, sinais[(ativo, candle)].loc[lambda s: s.index < fim])
        partes.append(a.assign(estrategia=f"{candle}m->{expiracao}m", expiracao=expiracao))
    return pd.concat(partes, ignore_index=True)


def diferenca(filtrada: pd.DataFrame, base: pd.DataFrame, payout: float = PAYOUT) -> dict:
    """Diferença por aposta da base (as mesmas linhas); abster vale 0. Blocos: ativo × dia."""
    d = pnl_digital(filtrada["direcao"].to_numpy(), filtrada["retorno"].to_numpy(), payout) - pnl_digital(base["direcao"].to_numpy(), base["retorno"].to_numpy(), payout)
    blocos = (base["ativo"] + "|" + pd.DatetimeIndex(base["tempo"]).floor("D").astype(str)).to_numpy()
    baixo, alto = intervalo_por_blocos(d, blocos)
    por_bloco = pd.Series(d).groupby(blocos).mean()
    erro = por_bloco.std(ddof=1) / np.sqrt(len(por_bloco))
    return {"diferenca": float(d.mean()), "ic95": (baixo, alto), "p_unilateral": float(norm.sf(por_bloco.mean() / erro)) if erro > 0 else 1.0,
            "abstencoes": int(((filtrada["direcao"] == 0) & (base["direcao"] != 0)).sum()), "apostas_base": int((base["direcao"] != 0).sum())}


def _metades(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    meio = pd.DatetimeIndex(df["tempo"]).sort_values()[len(df) // 2]
    return df[df["tempo"] < meio], df[df["tempo"] >= meio]


def _queda(df: pd.DataFrame, payout: float = PAYOUT) -> float:
    ordem = df.sort_values("tempo")
    acumulado = np.cumsum(pnl_digital(ordem["direcao"].to_numpy(), ordem["retorno"].to_numpy(), payout))
    return float(np.max(np.maximum.accumulate(np.concatenate([[0.0], acumulado]))[1:] - acumulado)) if len(acumulado) else 0.0


def p_contra_empate(a: pd.DataFrame) -> float:
    lado = np.sign(a["direcao"]) * np.sign(a["retorno"])
    ok = (a["direcao"] != 0) & (lado != 0)
    x = (lado[ok] > 0).astype(float) - EMPATE
    blocos = pd.DatetimeIndex(a.loc[ok, "tempo"]).floor("D")
    por_dia = x.groupby(blocos).mean()
    erro = por_dia.std(ddof=1) / np.sqrt(len(por_dia))
    return float(norm.sf(por_dia.mean() / erro)) if erro > 0 else 1.0


def carregar(raiz: str, ate: pd.Timestamp) -> dict:
    armazem = ArmazemVelas(raiz)
    return {a: armazem.ler(a, inicio=INICIO.to_pydatetime(), fim=ate.to_pydatetime()) for a in ATIVOS}


def explorar(raiz: str, pasta_motor: Path, saida: Path) -> dict:
    saida.mkdir(parents=True, exist_ok=True)
    velas = carregar(raiz, EXPLORACAO_ATE)  # nada depois do fim da exploração entra nesta fase
    resultado = {"protocolo": impressao_protocolo(), "candidatos": {}, "variantes": {}, "artefatos": {}}
    for nome, c in PROTOCOLO_C1["candidatos"].items():
        cand = treinar_candidato(velas[c["ativo"]], c["horizonte"])
        resultado["candidatos"][nome] = {"limiar": cand.limiar, "impressao": cand.impressao, **cand.exploracao}
        resultado["artefatos"][nome] = _guardar(cand, saida / f"{nome}.pkl")
        print(nome, resultado["candidatos"][nome], flush=True)
    estrategias = estrategias_base(pasta_motor)
    sinais = {(a, k): grade_de_sinais(velas[a], k) for a, k in {(a, k) for a, k, _, _ in estrategias}}
    filtradas, bases = {v: [] for v in VARIANTES}, []
    for ativo in ATIVOS:
        for h in (5, 15):
            previsoes, risco = risco_fora_da_amostra(velas[ativo], h)
            resultado["artefatos"][f"risco_{ativo}_{h}"] = _guardar(risco, saida / f"risco_{ativo}_{h}.pkl")
            inicio_oos = previsoes["p_extremo"].first_valid_index()
            base = base_motor(velas, sinais, [e for e in estrategias if e[0] == ativo and e[2] == h], inicio_oos, EXPLORACAO_ATE)
            bases.append(base)
            for variante in VARIANTES:
                filtradas[variante].append(filtrar_variante(base, previsoes, risco.limiares, variante))
            print(ativo, h, "apostas da base na exploração:", len(base), flush=True)
    base = pd.concat(bases, ignore_index=True)
    escolhidas = []
    for variante in VARIANTES:
        f = pd.concat(filtradas[variante], ignore_index=True)
        tudo = diferenca(f, base)
        b1, b2 = _metades(base)
        m1, m2 = diferenca(f.loc[b1.index], b1), diferenca(f.loc[b2.index], b2)
        passou = tudo["diferenca"] > 0 and tudo["ic95"][0] > 0 and m1["diferenca"] > 0 and m2["diferenca"] > 0
        resultado["variantes"][variante] = {**tudo, "metade1": m1["diferenca"], "metade2": m2["diferenca"], "passou_exploracao": passou}
        if passou:
            escolhidas.append((tudo["diferenca"], variante))
        print(variante, resultado["variantes"][variante], flush=True)
    resultado["variantes_para_confirmar"] = [v for _, v in sorted(escolhidas, reverse=True)[:PROTOCOLO_C1["variantes_max_para_confirmar"]]]
    (saida / "exploracao.json").write_text(json.dumps(resultado, indent=1, default=float, ensure_ascii=False), encoding="utf-8")
    return resultado


def confirmar(raiz: str, pasta_motor: Path, saida: Path) -> dict:
    exploracao = json.loads((saida / "exploracao.json").read_text(encoding="utf-8"))
    if exploracao["protocolo"] != impressao_protocolo():
        raise RuntimeError("o protocolo mudou depois da exploração")
    lacrar(saida)  # daqui em diante, este bloco não pode ser usado de novo com este protocolo
    inicio, fim = CONFIRMACAO
    velas = carregar(raiz, fim)
    resultado = {"protocolo": impressao_protocolo(), "candidatos": {}, "filtro": {}}
    estrategias = estrategias_base(pasta_motor)
    sinais = {(a, k): grade_de_sinais(velas[a], k) for a, k in {(a, k) for a, k, _, _ in estrategias}}
    ps = {}
    for nome, c in PROTOCOLO_C1["candidatos"].items():
        cand = _carregar(saida / f"{nome}.pkl", exploracao["artefatos"][nome])
        a = apostas_candidato(cand, velas[c["ativo"]], c["ativo"], inicio, fim)
        p = placar(a)
        m1, m2 = (placar(m) for m in _metades(a))
        ps[nome] = p_contra_empate(a)
        motor = {}
        for ativo, candle, expiracao, modelo in estrategias:
            if ativo == c["ativo"] and expiracao == c["horizonte"]:
                ref = apostas_motor(velas[ativo], modelo, ativo, candle, expiracao, inicio, fim, sinais[(ativo, candle)])
                motor[f"{candle}m->{expiracao}m"] = {"placar": placar(ref), "pareado": comparar(a, ref, PAYOUT)}
        resultado["candidatos"][nome] = {"placar": p, "metade1_acerto": m1["acerto"], "metade2_acerto": m2["acerto"], "p_contra_empate": ps[nome],
                                         "motor": motor}
    ajustados = dict(zip(ps, holm(list(ps.values()))))
    for nome, r in resultado["candidatos"].items():
        p = r["placar"]
        r["p_holm"] = ajustados[nome]
        r["criterios"] = {"acerto_ic_acima_do_empate": p["acerto_ic95"][0] > EMPATE, "expectativa_ic_acima_de_zero": p["expectativa_ic95"][PAYOUT][0] > 0,
                          "duas_metades": r["metade1_acerto"] > EMPATE and r["metade2_acerto"] > EMPATE, "holm": ajustados[nome] < 0.05}
        r["passou"] = all(r["criterios"].values())
    variantes = exploracao["variantes_para_confirmar"]
    if variantes:
        base_partes, filtradas = [], {v: [] for v in variantes}
        for ativo in ATIVOS:
            for h in (5, 15):
                risco = _carregar(saida / f"risco_{ativo}_{h}.pkl", exploracao["artefatos"][f"risco_{ativo}_{h}"])
                base = base_motor(velas, sinais, [e for e in estrategias if e[0] == ativo and e[2] == h], inicio, fim)
                previsoes = prever_risco(risco, velas[ativo], pd.DatetimeIndex(base["tempo"]))
                base_partes.append(base)
                for variante in variantes:
                    filtradas[variante].append(filtrar_variante(base, previsoes, risco.limiares, variante))
        base = pd.concat(base_partes, ignore_index=True)
        pv = {}
        for variante in variantes:
            f = pd.concat(filtradas[variante], ignore_index=True)
            tudo = diferenca(f, base)
            b1, b2 = _metades(base)
            pv[variante] = tudo["p_unilateral"]
            por_ativo = {a: diferenca(f[base["ativo"] == a], base[base["ativo"] == a]) for a in ATIVOS}
            sensibilidade = {str(pp): diferenca(f, base, pp)["diferenca"] for pp in PROTOCOLO_C1["payouts_sensibilidade"]}
            resultado["filtro"][variante] = {**tudo, "metade1": diferenca(f.loc[b1.index], b1)["diferenca"], "metade2": diferenca(f.loc[b2.index], b2)["diferenca"],
                                             "queda_com_filtro": _queda(f), "queda_sem_filtro": _queda(base), "por_ativo": por_ativo,
                                             "sensibilidade_payout": sensibilidade, "acerto_base": placar(base)["acerto"], "acerto_filtrado": placar(f)["acerto"],
                                             "expectativa_base": placar(base)["expectativa"][PAYOUT], "expectativa_filtrada": placar(f)["expectativa"][PAYOUT]}
        for variante, padj in zip(pv, holm(list(pv.values()))):
            r = resultado["filtro"][variante]
            r["p_holm"] = padj
            r["criterios"] = {"ic_acima_de_zero": r["ic95"][0] > 0, "duas_metades": r["metade1"] > 0 and r["metade2"] > 0,
                              "queda_nao_pior": r["queda_com_filtro"] <= r["queda_sem_filtro"], "holm": padj < 0.05}
            r["passou"] = all(r["criterios"].values())
    (saida / "confirmacao.json").write_text(json.dumps(resultado, indent=1, default=float, ensure_ascii=False), encoding="utf-8")
    return resultado


if __name__ == "__main__":
    fase, raiz, motor, destino = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
    {"explorar": explorar, "confirmar": confirmar}[fase](raiz, motor, destino)
