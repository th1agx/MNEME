"""C1: confirmação de ETH em 5 e 15 min e da volatilidade como filtro de "não operar". Pré-registro no Vault:
"E9 - confirmação C1 (ETH e filtro de volatilidade)", escrito em 11/11/2026 antes de qualquer cálculo na confirmação.

Os blocos são os da régua da Etapa 0 (`mneme.aprendizado`): exploração até 2026-02-01 e confirmação de 2026-02-01 a
2026-08-01. Tudo o que é treinado ou escolhido (modelos, limiares, variantes) usa só a exploração. A confirmação roda uma
vez: um lacre por impressão do protocolo recusa a segunda execução.

A referência é a política do motor reproduzida com os pesos atuais (técnicas × pesos, corte, uma aposta por vez). Esses
pesos foram treinados até 2026-07-31: no bloco de confirmação o motor está dentro da própria amostra e por isso é uma
referência otimista.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..aprendizado import EXPLORACAO_ATE, SELADO_DESDE
from ..laboratorio.confluencia import ATRASO, grade_de_sinais
from ..laboratorio.dataset import TEMPOS, alvos, construir
from ..laboratorio.horizontes import retorno_da_operacao, uma_por_vez
from ..laboratorio.validacao import dobras_walk_forward

CONFIRMACAO = (EXPLORACAO_ATE, SELADO_DESDE)
PARAMETROS_LGB = dict(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=300, subsample=0.8, subsample_freq=1,
                      colsample_bytree=0.8, random_state=0, n_jobs=1, deterministic=True, force_row_wise=True, verbose=-1)
PROTOCOLO_C1 = {
    "versao": "c1",
    "registrado_em": "2026-11-11",
    "exploracao": ["2024-11-01", str(EXPLORACAO_ATE.date())],
    "confirmacao": [str(CONFIRMACAO[0].date()), str(CONFIRMACAO[1].date())],
    "candidatos": {"C1a": {"ativo": "ETHUSDT", "horizonte": 5}, "C1b": {"ativo": "ETHUSDT", "horizonte": 15}},
    "limiar_candidato": "quantil 0,8 de |p-0,5| na última dobra do walk-forward da exploração",
    "uma_aposta_por_vez": True,
    "atraso_min": ATRASO,
    "lgb": {k: v for k, v in PARAMETROS_LGB.items() if k != "verbose"},
    "criterios_candidato": ["IC95 do acerto por dia > empate", "IC95 da expectativa a 85% > 0", "acerto > empate nas duas metades",
                            "p unilateral < 0,05 com Holm em {C1a, C1b}"],
    "base_filtro": "política do motor reproduzida em BTC, ETH e SOL, expiração fixa de 5 e 15 min",
    "variantes": {"V1": "P(extremo) >= q80", "V2": "P(extremo) <= q20", "V3": "vol prevista >= q80", "V4": "vol prevista <= q20"},
    "variantes_max_para_confirmar": 2,
    "escolha_variantes": "diferença de expectativa > 0 com IC inferior > 0 na exploração e > 0 nas duas metades da exploração",
    "criterios_filtro": ["IC95 da diferença de expectativa > 0", "diferença > 0 nas duas metades", "queda máxima com filtro <= sem filtro",
                         "p unilateral < 0,05 com Holm entre as variantes confirmadas"],
    "payout_principal": 0.85,
    "payouts_sensibilidade": [0.75, 0.80, 0.90],
}


def impressao_protocolo(protocolo: dict = PROTOCOLO_C1) -> str:
    return hashlib.sha256(json.dumps(protocolo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


class BlocoJaAberto(Exception):
    """O bloco de confirmação deste protocolo já foi usado. Abrir de novo seria ajustar olhando o resultado."""


def lacrar(pasta: Path | str, protocolo: dict = PROTOCOLO_C1) -> Path:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    lacre = pasta / f"lacre_{impressao_protocolo(protocolo)}.json"
    try:
        with lacre.open("x", encoding="utf-8") as saida:  # "x": falha se já existir, sem corrida
            json.dump({"aberto_em": datetime.now(timezone.utc).isoformat(), "protocolo": protocolo}, saida, ensure_ascii=False)
    except FileExistsError:
        raise BlocoJaAberto(f"o bloco de confirmação do protocolo {impressao_protocolo(protocolo)} já foi aberto ({lacre})") from None
    return lacre


# ---------- atributos e grade ----------

def grade(indice: pd.DatetimeIndex, minutos: int) -> pd.DatetimeIndex:
    return indice[(indice.hour * 60 + indice.minute + 1) % minutos == 0]


def atributos(v: pd.DataFrame) -> pd.DataFrame:
    """Atributos de vela do laboratório, sem as linhas de aquecimento."""
    x = construir(v)
    return x[x["v_retorno_240"].notna() & x[f"v_{TEMPOS[-1]}_adx"].notna()]


def _modelo(regressao: bool = False):
    return lgb.LGBMRegressor(**PARAMETROS_LGB) if regressao else lgb.LGBMClassifier(**PARAMETROS_LGB)


def _impressao_array(*arrays) -> str:
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(np.asarray(a, dtype=float)).tobytes())
    return h.hexdigest()[:12]


# ---------- candidato de direção ----------

@dataclass
class Candidato:
    horizonte: int
    modelo: object
    limiar: float
    impressao: str
    exploracao: dict = field(default_factory=dict)


def treinar_candidato(v: pd.DataFrame, horizonte: int, ate: pd.Timestamp = EXPLORACAO_ATE) -> Candidato:
    """Só vê velas antes de `ate`. O alvo segue a convenção do motor; o limiar sai das previsões fora da amostra da última dobra."""
    ve = v[v.index < ate]
    x = atributos(ve)
    tempos = grade(x.index, horizonte)
    ret = pd.Series(retorno_da_operacao(ve, tempos, ATRASO, horizonte), index=tempos)
    ret = ret[ret.notna() & (ret != 0)]
    x, y = x.loc[ret.index], (ret > 0).astype(int)
    dobras = dobras_walk_forward(len(x), 5, 1, 2)
    previsto, real = [], []
    for d in dobras:
        m = _modelo().fit(x.iloc[d.treino], y.iloc[d.treino])
        previsto.append(m.predict_proba(x.iloc[d.teste])[:, 1])
        real.append(y.iloc[d.teste].to_numpy())
    limiar = float(np.quantile(np.abs(previsto[-1] - 0.5), 0.8))
    final = _modelo().fit(x, y)
    p, r = np.concatenate(previsto[1:]), np.concatenate(real[1:])  # da segunda dobra em diante, cada uma com um limiar do passado
    escolhidos = np.abs(p - 0.5) >= limiar
    relatorio = {"amostras_treino": int(len(x)), "acerto_top_fora_da_amostra": float(((p >= 0.5) == (r == 1))[escolhidos].mean()),
                 "apostas_fora_da_amostra": int(escolhidos.sum())}
    return Candidato(horizonte, final, limiar, _impressao_array(x.to_numpy(), y.to_numpy(), [limiar]), relatorio)


def apostas_candidato(c: Candidato, v: pd.DataFrame, ativo: str, inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DataFrame:
    """As apostas do candidato no bloco [inicio, fim): só velas da grade, com saída antes do fim, uma por vez."""
    x = atributos(v[v.index < fim])
    tempos = grade(x.index[x.index >= inicio], c.horizonte)
    p = c.modelo.predict_proba(x.loc[tempos])[:, 1]
    escolhidos = np.abs(p - 0.5) >= c.limiar
    tempos, direcao = tempos[escolhidos], np.where(p[escolhidos] >= 0.5, 1, -1)
    return _apostas(v[v.index < fim], ativo, tempos, direcao, c.horizonte)


def _apostas(v: pd.DataFrame, ativo: str, tempos: pd.DatetimeIndex, direcao: np.ndarray, expiracao: int) -> pd.DataFrame:
    aceitos = uma_por_vez(pd.DatetimeIndex(tempos), ATRASO, expiracao)
    tempos, direcao = pd.DatetimeIndex(tempos)[aceitos], np.asarray(direcao)[aceitos]
    ret = retorno_da_operacao(v, tempos, ATRASO, expiracao)
    a = pd.DataFrame({"ativo": ativo, "tempo": tempos, "direcao": direcao.astype(float), "retorno": ret})
    return a[a["retorno"].notna()].reset_index(drop=True)


# ---------- referência: a política do motor ----------

def politica_motor(v: pd.DataFrame, modelo: dict, candle: int, expiracao: int, sinais: pd.DataFrame | None = None,
                   uma_por_vez_: bool = True) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """A mesma conta de `confluencia.decidir` em todas as velas de uma vez: soma ponderada, logística e corte."""
    sinais = grade_de_sinais(v, candle) if sinais is None else sinais
    x = sinais.reindex(columns=modelo["tecnicas"]).fillna(0).to_numpy(dtype=float)
    prob = 1 / (1 + np.exp(-(modelo["intercepto"] + x @ np.asarray(modelo["pesos"]))))
    opera = np.abs(prob - 0.5) >= modelo["corte"]
    tempos, direcao = sinais.index[opera], np.where(prob[opera] >= 0.5, 1, -1)
    if uma_por_vez_:
        aceitos = uma_por_vez(tempos, ATRASO, expiracao)
        tempos, direcao = tempos[aceitos], direcao[aceitos]
    return tempos, direcao


def apostas_motor(v: pd.DataFrame, modelo: dict, ativo: str, candle: int, expiracao: int, inicio: pd.Timestamp, fim: pd.Timestamp,
                  sinais: pd.DataFrame | None = None) -> pd.DataFrame:
    tempos, direcao = politica_motor(v[v.index < fim], modelo, candle, expiracao, sinais, uma_por_vez_=False)
    dentro = tempos >= inicio
    return _apostas(v[v.index < fim], ativo, tempos[dentro], direcao[dentro], expiracao)


# ---------- risco: volatilidade e extremos ----------

def _alvos_risco(v: pd.DataFrame, horizonte: int) -> pd.DataFrame:
    y = alvos(v, horizonte)
    passos = np.log(v["fechamento"]).diff()
    esperado = passos.rolling(max(60, horizonte)).std() * np.sqrt(horizonte)
    y["extremo"] = (y["retorno"].abs() > 2 * esperado.reindex(y.index)).astype(float).where(y["retorno"].notna() & esperado.notna())
    return y[["extremo", "vol_futura"]]


@dataclass
class Risco:
    horizonte: int
    extremo: object
    vol: object
    limiares: dict
    impressao: str


def risco_fora_da_amostra(v: pd.DataFrame, horizonte: int, ate: pd.Timestamp = EXPLORACAO_ATE) -> tuple[pd.DataFrame, Risco]:
    """Previsões de risco fora da amostra em cada minuto da exploração (walk-forward na grade) e os modelos finais.

    Os limiares (q20 e q80) saem das previsões da última dobra, na grade. Os modelos finais usam toda a exploração.
    """
    ve = v[v.index < ate]
    x_todos = atributos(ve)
    y = _alvos_risco(ve, horizonte).reindex(x_todos.index)
    g = grade(x_todos.index, horizonte)
    g = g[y.loc[g, "extremo"].notna() & y.loc[g, "vol_futura"].notna()]
    dobras = dobras_walk_forward(len(g), 5, 1, 2)
    previsoes = pd.DataFrame(np.nan, index=x_todos.index, columns=["p_extremo", "vol_prevista"])
    ultima = None
    for i, d in enumerate(dobras):
        treino, teste = g[d.treino], g[d.teste]
        me = _modelo().fit(x_todos.loc[treino], y.loc[treino, "extremo"].astype(int))
        mv = _modelo(regressao=True).fit(x_todos.loc[treino], y.loc[treino, "vol_futura"])
        fim_teste = g[d.teste[-1] + 1] if d.teste[-1] + 1 < len(g) else ate
        minutos = x_todos.index[(x_todos.index >= teste[0]) & (x_todos.index < fim_teste)]
        previsoes.loc[minutos, "p_extremo"] = me.predict_proba(x_todos.loc[minutos])[:, 1]
        previsoes.loc[minutos, "vol_prevista"] = mv.predict(x_todos.loc[minutos])
        if i == len(dobras) - 1:
            ultima = previsoes.loc[teste]
    limiares = {"p_extremo": (float(ultima["p_extremo"].quantile(0.2)), float(ultima["p_extremo"].quantile(0.8))),
                "vol_prevista": (float(ultima["vol_prevista"].quantile(0.2)), float(ultima["vol_prevista"].quantile(0.8)))}
    me = _modelo().fit(x_todos.loc[g], y.loc[g, "extremo"].astype(int))
    mv = _modelo(regressao=True).fit(x_todos.loc[g], y.loc[g, "vol_futura"])
    return previsoes, Risco(horizonte, me, mv, limiares, _impressao_array(y.loc[g].to_numpy(), list(limiares["p_extremo"]) + list(limiares["vol_prevista"])))


def prever_risco(r: Risco, v: pd.DataFrame, tempos: pd.DatetimeIndex) -> pd.DataFrame:
    x = atributos(v)
    tempos = pd.DatetimeIndex(tempos).intersection(x.index)
    return pd.DataFrame({"p_extremo": r.extremo.predict_proba(x.loc[tempos])[:, 1], "vol_prevista": r.vol.predict(x.loc[tempos])}, index=tempos)


VARIANTES = {"V1": ("p_extremo", "acima"), "V2": ("p_extremo", "abaixo"), "V3": ("vol_prevista", "acima"), "V4": ("vol_prevista", "abaixo")}


def aplicar_filtro(base: pd.DataFrame, risco: pd.Series, acima_de: float | None = None, abaixo_de: float | None = None) -> pd.DataFrame:
    """Só zera a direção onde o risco cruza o limite. Sem previsão de risco, mantém a aposta."""
    valor = risco.reindex(pd.DatetimeIndex(base["tempo"])).to_numpy()
    abster = np.zeros(len(base), dtype=bool)
    if acima_de is not None:
        abster |= valor >= acima_de
    if abaixo_de is not None:
        abster |= valor <= abaixo_de
    return base.assign(direcao=np.where(abster, 0.0, base["direcao"].to_numpy()))


def filtrar_variante(base: pd.DataFrame, previsoes: pd.DataFrame, limiares: dict, variante: str) -> pd.DataFrame:
    coluna, lado = VARIANTES[variante]
    q20, q80 = limiares[coluna]
    return aplicar_filtro(base, previsoes[coluna], acima_de=q80 if lado == "acima" else None, abaixo_de=q20 if lado == "abaixo" else None)
