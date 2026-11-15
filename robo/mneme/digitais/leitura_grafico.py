"""O que o MNEME está lendo e prevendo, para o gráfico do card da extensão. Só mostra: nada aqui decide ou opera.

- Linhas: as mesmas leituras que o motor usa (pivôs, suporte e resistência, linhas de tendência, Fibonacci da última
  perna, VWAP do dia e o preço de maior volume das últimas 96 velas).
- Previsão: a probabilidade de subir pela conta exata do motor (`confluencia.decidir`, com os pesos da estratégia) e um
  cone de onde o preço pode estar nos próximos minutos, pela volatilidade da última hora (faixas de 68% e 95%). O cone não
  tem tendência de propósito: o que o MNEME prevê bem é o tamanho do movimento, não o caminho.
- Anterior: o cone e a probabilidade da vela anterior e o que de fato aconteceu, para ver ao vivo se acertou.

Tudo usa só velas fechadas até `agora`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicadores as ind
from ..laboratorio.confluencia import grade_de_sinais
from ..leitura import atributos, pivos

VELAS_NO_GRAFICO = 72
LADOS = 3
JANELA_VOL = 60
Z68, Z95 = 1.0, 1.96


def _n(x) -> float | None:
    return None if x is None or not np.isfinite(x) else float(round(float(x), 6))


def _prob(modelo: dict, linha: pd.Series) -> float:
    x = linha.reindex(modelo["tecnicas"]).fillna(0).to_numpy(dtype=float)
    return float(1 / (1 + np.exp(-(modelo["intercepto"] + x @ np.asarray(modelo["pesos"])))))


def _sigma(v: pd.DataFrame, ate: pd.Timestamp) -> float | None:
    passado = v[v.index <= ate]
    return float(np.log(passado["fechamento"]).diff().tail(JANELA_VOL).std()) if len(passado) > JANELA_VOL else None


def _cenarios(p0: float, sigma: float, pontos: int, semente: int, quantos: int = 5) -> list[list[float]]:
    """Caminhos possíveis sorteados com a volatilidade da última hora. São ilustração da incerteza, não previsão do caminho."""
    r = np.random.default_rng(semente)
    passos = r.normal(0.0, sigma, (quantos, pontos))
    return [[_n(x) for x in p0 * np.exp(np.cumsum(c))] for c in passos]


def _cone(v: pd.DataFrame, ate: pd.Timestamp, minutos: int) -> tuple[float, list[dict]] | None:
    """Faixas a partir do fechamento da vela de 1 min que abriu em `ate`, para 1 a `minutos` minutos à frente."""
    passado = v[v.index <= ate]
    sigma = _sigma(v, ate)
    if sigma is None:
        return None
    p0 = float(passado["fechamento"].iloc[-1])
    pontos = []
    for k in range(1, minutos + 1):
        s = sigma * np.sqrt(k)
        pontos.append({"t": (ate + pd.Timedelta(minutes=1 + k)).isoformat(), "lo68": _n(p0 * np.exp(-Z68 * s)), "hi68": _n(p0 * np.exp(Z68 * s)),
                       "lo95": _n(p0 * np.exp(-Z95 * s)), "hi95": _n(p0 * np.exp(Z95 * s))})
    return p0, pontos


def _linha_de_tendencia(pontos: pd.Series, maior: pd.DataFrame, subir: bool, fim: pd.Timestamp) -> dict | None:
    """Reta pelos dois últimos pivôs confirmados, levada até `fim`. Só a de alta sobe e só a de baixa desce."""
    if len(pontos) < 2:
        return None
    (t1, y1), (t2, y2) = pontos.iloc[-2:].items()
    passo = (y2 - y1) / ((t2 - t1) / pd.Timedelta(minutes=1))
    if (subir and passo <= 0) or (not subir and passo >= 0):
        return None
    y_fim = y2 + passo * ((fim - t2) / pd.Timedelta(minutes=1))
    return {"t1": t1.isoformat(), "y1": _n(y1), "t2": fim.isoformat(), "y2": _n(y_fim)}


def leitura(v: pd.DataFrame, candle: int, expiracao: int, modelo: dict, agora: pd.Timestamp) -> dict:
    v = v[v.index + pd.Timedelta(minutes=1) <= agora]  # só velas fechadas
    maior = ind.reamostrar(v.dropna(subset=["fechamento"]), f"{candle}min")
    a = atributos(maior)
    ultimas = maior.tail(VELAS_NO_GRAFICO)
    velas = [{"t": t.isoformat(), "ab": _n(r.abertura), "max": _n(r.maxima), "min": _n(r.minima), "fe": _n(r.fechamento)} for t, r in ultimas.iterrows()]

    # Pivôs: o valor aparece LADOS velas depois do pivô; a reta usa a hora em que o pivô aconteceu.
    p = pivos(maior, LADOS)
    def confirmados(coluna):
        s = p[coluna].dropna()
        return pd.Series(s.to_numpy(), index=[maior.index[maior.index.get_loc(t) - LADOS] for t in s.index])
    topos, fundos = confirmados("topo"), confirmados("fundo")
    fim = v.index[-1] + pd.Timedelta(minutes=1 + expiracao)

    fib = None
    if len(topos) and len(fundos):
        topo, fundo = float(topos.iloc[-1]), float(fundos.iloc[-1])
        sobe = fundos.index[-1] < topos.index[-1]  # a última perna foi de alta
        perna = topo - fundo
        niveis = {str(k): _n(topo - k * perna if sobe else fundo + k * perna) for k in (0.382, 0.5, 0.618, 0.786)}
        fib = {"sentido": "alta" if sobe else "baixa", "niveis": niveis, "zona_dourada": [niveis["0.5"], niveis["0.786"]]}

    poc = None
    janela = maior.tail(96)
    if len(janela) == 96 and janela["volume"].sum() > 0:
        tipico = ((janela["maxima"] + janela["minima"] + janela["fechamento"]) / 3).to_numpy()
        hist, bordas = np.histogram(tipico, 24, weights=janela["volume"].to_numpy())
        topo_hist = int(hist.argmax())
        poc = _n((bordas[topo_hist] + bordas[topo_hist + 1]) / 2)

    vwap = [{"t": t.isoformat(), "v": _n(x)} for t, x in a["vwap"].tail(VELAS_NO_GRAFICO).items() if np.isfinite(x)]
    linhas = {"suporte": _n(a["suporte"].iloc[-1]) if len(a) else None, "resistencia": _n(a["resistencia"].iloc[-1]) if len(a) else None,
              "lta": _linha_de_tendencia(fundos, maior, True, fim), "ltb": _linha_de_tendencia(topos, maior, False, fim),
              "fibonacci": fib, "vwap": vwap or None, "poc": poc,
              "degraus": [{"t": t.isoformat(), "suporte": _n(a.at[t, "suporte"]), "resistencia": _n(a.at[t, "resistencia"])} for t in ultimas.index]}

    sinais = grade_de_sinais(v, candle)
    previsao, anterior = None, None
    if len(sinais):
        vela = sinais.index[-1]
        prob = _prob(modelo, sinais.iloc[-1])
        cone = _cone(v, v.index[-1], expiracao + 1)
        linha = sinais.iloc[-1]
        sigma = _sigma(v, v.index[-1])
        previsao = {"vela": vela.isoformat(), "prob_sobe": prob, "corte": modelo["corte"],
                    "tecnicas": {"alta": int((linha > 0).sum()), "baixa": int((linha < 0).sum()), "total": int(len(linha))},
                    "sigma_1min": _n(sigma),
                    "cenarios": _cenarios(cone[0], sigma, len(cone[1]), int(vela.timestamp())) if cone and sigma else [],
                    "direcao": ("CALL" if prob >= 0.5 else "PUT") if abs(prob - 0.5) >= modelo["corte"] else None,
                    "preco": _n(cone[0]) if cone else None, "cone": cone[1] if cone else []}
        if len(sinais) > 1:
            t_ant = sinais.index[-2]
            cone_ant = _cone(v, t_ant, expiracao)
            alvo = t_ant + pd.Timedelta(minutes=expiracao)
            realizado = float(v.loc[alvo, "fechamento"]) if alvo in v.index else None
            if cone_ant:
                ultimo = cone_ant[1][-1]
                anterior = {"vela": t_ant.isoformat(), "prob_sobe": _prob(modelo, sinais.iloc[-2]), "preco": _n(cone_ant[0]), "cone": cone_ant[1],
                            "realizado": _n(realizado),
                            "dentro_68": None if realizado is None else bool(ultimo["lo68"] <= realizado <= ultimo["hi68"]),
                            "subiu": None if realizado is None else realizado > cone_ant[0]}
    return {"agora": agora.isoformat(), "candle": candle, "expiracao": expiracao, "velas": velas, "linhas": linhas, "previsao": previsao, "anterior": anterior}
