"""M1: leituras próprias de moeda no bloco de exploração (antes de 2026-02-01). Registro em estudos/e9/registro_m1_moedas.json.

    MNEME_DADOS_MERCADO=dados/mercado .venv/bin/python estudos/e9/rodar_m1.py   # grava dados/e9/m1_moedas.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

PARES = {"EURUSD": -1, "GBPUSD": -1, "USDJPY": 1, "USDCAD": 1}  # sinal do lado do dólar
FIM_EXPLORACAO = "2026-02-01"
EXP = 5
EMPATE = 1 / 1.85
SESSOES = [("asia", 0, 7), ("londres", 7, 12), ("londres_ny", 12, 16), ("ny", 16, 21), ("fechamento", 21, 24)]
FAMILIA = 24
SORTEIOS = 5000


def carregar(raiz: Path, par: str) -> pd.Series:
    arquivos = sorted(a for a in (raiz / "velas_1m" / par).glob("*.parquet") if a.stem < FIM_EXPLORACAO)
    v = pd.concat([pd.read_parquet(a, columns=["abertura_em", "abertura", "fechamento"]) for a in arquivos])
    v = v.drop_duplicates("abertura_em").set_index("abertura_em").sort_index()
    return v


def sem_sobreposicao(tempos: np.ndarray, passo: np.timedelta64) -> np.ndarray:
    """Uma aposta por vez: a próxima só depois que a anterior expirou."""
    ok, ultimo = np.zeros(len(tempos), dtype=bool), None
    for i, t in enumerate(tempos):
        if ultimo is None or t >= ultimo + passo:
            ok[i], ultimo = True, t
    return ok


def placar(acertos: pd.Series, semente: int = 7) -> dict:
    a = acertos.dropna()
    if a.empty:
        return {"apostas": 0}
    por = a.groupby(a.index.date).agg(["sum", "count"])
    r = np.random.default_rng(semente).integers(0, len(por), (SORTEIOS, len(por)))
    s = por["sum"].to_numpy()[r].sum(1) / por["count"].to_numpy()[r].sum(1)
    return {"apostas": int(len(a)), "acerto": float(a.mean()), "dias": int(len(por)),
            "limite_baixo_95": float(np.quantile(s, 0.05)), "limite_baixo_familia": float(np.quantile(s, 0.05 / FAMILIA)),
            "passa_corrigido": bool(np.quantile(s, 0.05 / FAMILIA) > EMPATE), "passa_sem_correcao": bool(np.quantile(s, 0.05) > EMPATE)}


def resultado(fech: pd.Series, tempos: pd.DatetimeIndex, direcao: np.ndarray) -> pd.Series:
    """Ganha se o preço 5 minutos depois do fechamento da vela t andou na direção apostada; sem movimento é empate (fora)."""
    futuro = fech.reindex(tempos + pd.Timedelta(minutes=EXP)).to_numpy()
    agora = fech.reindex(tempos).to_numpy()
    mov = np.sign(futuro - agora)
    g = np.where(np.isnan(mov) | (mov == 0), np.nan, (mov == direcao).astype(float))
    return pd.Series(g, index=tempos)


def main() -> None:
    raiz = Path(os.getenv("MNEME_DADOS_MERCADO", "dados/mercado"))
    velas = {p: carregar(raiz, p) for p in PARES}
    grade = pd.date_range(min(v.index[0] for v in velas.values()), max(v.index[-1] for v in velas.values()), freq="1min")
    fech = pd.DataFrame({p: v["fechamento"].reindex(grade) for p, v in velas.items()})
    lado = np.log(fech).diff(EXP) * pd.Series(PARES)  # movimento de 5 min do lado do dólar
    saida = {"registro": "estudos/e9/registro_m1_moedas.json", "periodo": [str(grade[0]), str(grade[-1])], "F1": {}, "F1_placebo": {}, "F2": {}}

    for p, s in PARES.items():
        outros = [q for q in PARES if q != p]
        for nome, fator in (("F1", lado[outros].mean(axis=1, skipna=False)), ("F1_placebo", lado[outros].mean(axis=1, skipna=False).shift(60))):
            atraso = (fator - lado[p]).dropna()
            limite = atraso.abs().rolling(1440, min_periods=720).quantile(0.9).shift(1)
            cand = atraso[(atraso.abs() >= limite) & atraso.ne(0)]
            ok = sem_sobreposicao(cand.index.to_numpy(), np.timedelta64(EXP, "m"))
            cand = cand[ok]
            direcao = s * np.sign(cand.to_numpy())
            saida[nome][p] = placar(resultado(fech[p], cand.index, direcao))

        v = velas[p]
        corpo = (v["fechamento"] - v["abertura"])
        corpo = corpo[corpo != 0]
        ok = sem_sobreposicao(corpo.index.to_numpy(), np.timedelta64(EXP, "m"))
        corpo = corpo[ok]
        g = resultado(fech[p], corpo.index, -np.sign(corpo.to_numpy()))
        hora = g.index.hour
        saida["F2"][p] = {nome: placar(g[(hora >= a) & (hora < b)]) for nome, a, b in SESSOES}
        saida["F2"][p]["todas"] = placar(g)

    destino = Path(os.getenv("MNEME_DADOS", "dados")) / "e9" / "m1_moedas.json"
    destino.write_text(json.dumps(saida, indent=1, ensure_ascii=False), encoding="utf-8")
    for f in ("F1", "F1_placebo"):
        for p, r in saida[f].items():
            print(f"{f:10} {p}: {r.get('apostas')} apostas, {r.get('acerto', 0):.3%}, baixo95 {r.get('limite_baixo_95', 0):.3%}, corrigido {r.get('limite_baixo_familia', 0):.3%}")
    for p, ss in saida["F2"].items():
        print(f"F2 {p}: " + " | ".join(f"{k} {r.get('acerto', 0):.1%} ({r.get('apostas')}) {'✓' if r.get('passa_corrigido') else '·'}" for k, r in ss.items()))


if __name__ == "__main__":
    main()
