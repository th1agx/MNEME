"""Metodologias de leitura do mercado como evidências numéricas para a inteligência central.

Aqui nada decide. Cada função escreve em colunas uma interpretação formal de uma escola de análise, sem olhar o futuro.
Quem aprende quando cada evidência importa é o modelo; quem decide é o caminho único de decisão. Várias escolas têm definições
abertas: estas são as nossas regras, testáveis, e a documentação de cada uma está em `robo/conhecimento/metodologias.md`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .leitura import pivos

LADOS = 3


def _escala(atr: pd.Series) -> pd.Series:
    return atr.replace(0, np.nan)


def fibonacci(v: pd.DataFrame, atr: pd.Series) -> pd.DataFrame:
    """Retração dentro da última perna confirmada entre um topo e um fundo."""
    p = pivos(v, LADOS)
    topo, fundo = p["topo"].ffill(), p["fundo"].ffill()
    posicoes = pd.Series(np.arange(len(v)), index=v.index)
    quando_topo = posicoes.where(p["topo"].notna()).ffill()
    quando_fundo = posicoes.where(p["fundo"].notna()).ffill()
    sobe = quando_fundo < quando_topo  # o último extremo foi um topo: a perna mais recente foi de alta
    perna = (topo - fundo).replace(0, np.nan)
    f = v["fechamento"]
    retracao = ((topo - f) / perna).where(sobe, (f - fundo) / perna)
    nivel_618 = (topo - 0.618 * perna).where(sobe, fundo + 0.618 * perna)
    x = pd.DataFrame({"fib_retracao": retracao, "fib_sentido": np.where(quando_fundo.isna() | quando_topo.isna(), 0, np.where(sobe, 1, -1)),
                      "fib_dist_618": (f - nivel_618) / _escala(atr), "fib_zona_dourada": retracao.between(0.5, 0.786).astype(int)}, index=v.index)
    return x


def fair_value_gaps(v: pd.DataFrame, atr: pd.Series) -> pd.DataFrame:
    """Último desequilíbrio de 3 velas ainda não invalidado por um fechamento além dele. Distância em ATR."""
    h, l, c = v["maxima"].to_numpy(), v["minima"].to_numpy(), v["fechamento"].to_numpy()
    alta, baixa = np.full(len(v), np.nan), np.full(len(v), np.nan)
    ativo_alta, ativo_baixa = np.nan, np.nan
    for t in range(2, len(v)):
        if l[t] > h[t - 2]:
            ativo_alta = l[t]
        if h[t] < l[t - 2]:
            ativo_baixa = h[t]
        if not np.isnan(ativo_alta) and c[t] < ativo_alta:
            ativo_alta = np.nan if c[t] < h[t - 2] else ativo_alta
        if not np.isnan(ativo_baixa) and c[t] > ativo_baixa:
            ativo_baixa = np.nan if c[t] > l[t - 2] else ativo_baixa
        alta[t], baixa[t] = ativo_alta, ativo_baixa
    escala = _escala(atr)
    return pd.DataFrame({"fvg_alta_dist": (v["fechamento"] - alta) / escala, "fvg_baixa_dist": (baixa - v["fechamento"]) / escala}, index=v.index)


def order_blocks(v: pd.DataFrame, atr: pd.Series, rompimento: pd.Series, busca: int = 10) -> pd.DataFrame:
    """Última vela contrária antes de um rompimento de estrutura. A zona vale até um fechamento além dela."""
    a, h, l, c = (v[k].to_numpy() for k in ("abertura", "maxima", "minima", "fechamento"))
    rompeu = rompimento.to_numpy()
    alta, baixa = np.full(len(v), np.nan), np.full(len(v), np.nan)
    zona_alta, zona_baixa = np.nan, np.nan
    for t in range(len(v)):
        if rompeu[t] > 0:
            for j in range(t - 1, max(t - busca, -1), -1):
                if c[j] < a[j]:
                    zona_alta = h[j]
                    fundo_alta = l[j]
                    break
        elif rompeu[t] < 0:
            for j in range(t - 1, max(t - busca, -1), -1):
                if c[j] > a[j]:
                    zona_baixa = l[j]
                    topo_baixa = h[j]
                    break
        if not np.isnan(zona_alta) and c[t] < fundo_alta:
            zona_alta = np.nan
        if not np.isnan(zona_baixa) and c[t] > topo_baixa:
            zona_baixa = np.nan
        alta[t], baixa[t] = zona_alta, zona_baixa
    escala = _escala(atr)
    return pd.DataFrame({"ob_alta_dist": (v["fechamento"] - alta) / escala, "ob_baixa_dist": (baixa - v["fechamento"]) / escala}, index=v.index)


def ichimoku(v: pd.DataFrame, atr: pd.Series) -> pd.DataFrame:
    """A nuvem usada em cada vela é a que foi desenhada 26 velas antes, como no gráfico. Nada é projetado para o passado."""
    h, l, f = v["maxima"], v["minima"], v["fechamento"]
    meio = lambda n: (h.rolling(n).max() + l.rolling(n).min()) / 2
    tenkan, kijun = meio(9), meio(26)
    span_a, span_b = ((tenkan + kijun) / 2).shift(26), meio(52).shift(26)
    topo, base = pd.concat([span_a, span_b], axis=1).max(axis=1, skipna=False), pd.concat([span_a, span_b], axis=1).min(axis=1, skipna=False)
    posicao = pd.Series(np.where(f > topo, 1, np.where(f < base, -1, 0)), index=v.index).where(topo.notna())
    escala = _escala(atr)
    return pd.DataFrame({"ichi_tk": (tenkan - kijun) / escala, "ichi_nuvem_pos": posicao, "ichi_espessura": (topo - base) / escala, "ichi_nuvem_cor": np.sign(span_a - span_b)}, index=v.index)


def linhas_de_tendencia(v: pd.DataFrame, atr: pd.Series) -> pd.DataFrame:
    """Reta pelos dois últimos fundos e pelos dois últimos topos confirmados, projetada até a vela atual."""
    p = pivos(v, LADOS)
    f = v["fechamento"].to_numpy()
    n = len(v)
    saida = {}
    for coluna, nome in (("fundo", "lt_alta"), ("topo", "lt_baixa")):
        valores = p[coluna].to_numpy()
        inclinacao, distancia = np.full(n, np.nan), np.full(n, np.nan)
        anterior = ultimo = None
        for t in range(n):
            if not np.isnan(valores[t]):
                anterior, ultimo = ultimo, (t - LADOS, valores[t])  # o pivô ocorreu LADOS velas antes de ser confirmado
            if anterior is not None and ultimo[0] > anterior[0]:
                passo = (ultimo[1] - anterior[1]) / (ultimo[0] - anterior[0])
                inclinacao[t] = passo
                distancia[t] = f[t] - (ultimo[1] + passo * (t - ultimo[0]))
        saida[f"{nome}_inclinacao"] = pd.Series(inclinacao, index=v.index) / _escala(atr)
        saida[f"{nome}_dist"] = pd.Series(distancia, index=v.index) / _escala(atr)
    return pd.DataFrame(saida, index=v.index)


def perfil_de_volume(v: pd.DataFrame, atr: pd.Series, janela: int = 96, faixas: int = 24) -> pd.DataFrame:
    """Ponto de maior volume (POC) e área de valor de 70% nas últimas `janela` velas."""
    tipico = ((v["maxima"] + v["minima"] + v["fechamento"]) / 3).to_numpy(dtype="float64")
    volume, f = v["volume"].to_numpy(dtype="float64"), v["fechamento"].to_numpy(dtype="float64")
    poc, dentro = np.full(len(v), np.nan), np.full(len(v), np.nan)
    if len(v) >= janela:
        # Todas as janelas de uma vez, com as mesmas contas do np.histogram de faixas iguais: o resultado é idêntico ao laço.
        precos = np.lib.stride_tricks.sliding_window_view(tipico, janela)
        pesos = np.lib.stride_tricks.sliding_window_view(volume, janela)
        validas = ~np.isnan(precos).any(axis=1) & (pesos.sum(axis=1) != 0)
        linhas = np.flatnonzero(validas)
        precos, pesos = precos[linhas], pesos[linhas]
        primeira, ultima = precos.min(axis=1), precos.max(axis=1)
        iguais = primeira == ultima
        primeira, ultima = np.where(iguais, primeira - 0.5, primeira), np.where(iguais, ultima + 0.5, ultima)
        bordas = np.linspace(primeira, ultima, faixas + 1, endpoint=True, axis=1)
        indices = (((precos - primeira[:, None]) / (ultima - primeira)[:, None]) * faixas).astype(np.intp)
        indices[indices == faixas] -= 1
        indices -= precos < np.take_along_axis(bordas, indices, axis=1)
        indices += (precos >= np.take_along_axis(bordas, indices + 1, axis=1)) & (indices != faixas - 1)
        hist = np.bincount((indices + faixas * np.arange(len(linhas))[:, None]).ravel(), weights=pesos.ravel(),
                           minlength=len(linhas) * faixas).reshape(len(linhas), faixas)
        meios = (bordas[:, :-1] + bordas[:, 1:]) / 2
        topo = hist.argmax(axis=1)
        ordem = np.argsort(hist, axis=1)[:, ::-1]
        acumulado = np.cumsum(np.take_along_axis(hist, ordem, axis=1), axis=1)
        alvo = 0.7 * hist.sum(axis=1)
        quantas = np.array([np.searchsorted(a, x) for a, x in zip(acumulado, alvo)], dtype=np.intp) + 1
        escolhidos = np.take_along_axis(meios, ordem, axis=1)
        dentro_da_conta = np.arange(faixas)[None, :] < quantas[:, None]
        baixo = np.where(dentro_da_conta, escolhidos, np.inf).min(axis=1)
        alto = np.where(dentro_da_conta, escolhidos, -np.inf).max(axis=1)
        t = linhas + janela - 1
        poc[t] = np.take_along_axis(meios, topo[:, None], axis=1)[:, 0]
        dentro[t] = ((baixo <= f[t]) & (f[t] <= alto)).astype(float)
    return pd.DataFrame({"vp_dist_poc": (v["fechamento"] - poc) / _escala(atr), "vp_na_area_valor": dentro}, index=v.index)


def eventos_de_liquidez(v: pd.DataFrame, a: pd.DataFrame) -> pd.DataFrame:
    """Varredura de liquidez, spring de Wyckoff e topo ou fundo duplo, a partir dos níveis que já existiam antes da vela."""
    resistencia, suporte = a["resistencia"].shift(), a["suporte"].shift()
    f = v["fechamento"]
    varredura = ((v["minima"] < suporte) & (f > suporte)).astype(int) - ((v["maxima"] > resistencia) & (f < resistencia)).astype(int)
    consolidou = a["consolidacao"].shift().rolling(20).max().fillna(0) > 0
    spring = varredura.where(consolidou, 0)
    p = pivos(v, LADOS)
    topos, fundos = p["topo"].dropna(), p["fundo"].dropna()
    atr = a["atr_14"]
    topo_duplo = (topos.diff().abs().reindex(v.index).ffill() < 0.5 * atr) & (f < resistencia)
    fundo_duplo = (fundos.diff().abs().reindex(v.index).ffill() < 0.5 * atr) & (f > suporte)
    return pd.DataFrame({"liq_varredura": varredura, "wyckoff_spring": spring, "padrao_duplo": fundo_duplo.astype(int) - topo_duplo.astype(int)}, index=v.index)


def evidencias(v: pd.DataFrame, a: pd.DataFrame) -> pd.DataFrame:
    """Todas as metodologias já formalizadas, para `v` e seus atributos `a` no mesmo tempo gráfico."""
    atr = a["atr_14"]
    return pd.concat([fibonacci(v, atr), fair_value_gaps(v, atr), order_blocks(v, atr, a["rompimento"]), ichimoku(v, atr),
                      linhas_de_tendencia(v, atr), perfil_de_volume(v, atr), eventos_de_liquidez(v, a)], axis=1)
