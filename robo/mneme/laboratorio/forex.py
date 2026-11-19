"""Pesquisa Forex por diferenca de preco, com BID/ASK e sem payout binario.

Nao executa ordens. Cada estrategia tem uma carteira contrafactual independente.
O modelo so pode aprender com operacoes ja encerradas antes de seu treino.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class RegraSaida:
    stop_atr: float = 1.5
    alvo_atr: float | None = 3.0
    minutos: int | None = 15
    trailing_atr: float | None = None
    ativar_trailing_atr: float = 1.0

    def __post_init__(self):
        if self.stop_atr <= 0 or (self.alvo_atr is not None and self.alvo_atr <= 0):
            raise ValueError("Distancias de stop/alvo precisam ser positivas.")
        if self.minutos is not None and self.minutos < 1:
            raise ValueError("Duracao precisa ser positiva.")
        if self.trailing_atr is not None and (self.trailing_atr <= 0 or self.ativar_trailing_atr <= 0):
            raise ValueError("Trailing precisa de distancias positivas.")


def conferir_cotacoes(bid: pd.DataFrame, ask: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Alinha apenas minutos com os dois lados. Nunca inventa ASK nem preenche lacunas."""
    if not bid.index.is_unique or not ask.index.is_unique:
        raise ValueError("Minutos duplicados nas cotacoes.")
    if not bid.index.is_monotonic_increasing or not ask.index.is_monotonic_increasing:
        raise ValueError("Cotacoes fora de ordem.")
    if bid.index.tz is None or ask.index.tz is None:
        raise ValueError("Cotacoes precisam de fuso horario.")
    comuns = bid.index.intersection(ask.index)
    b, a = bid.loc[comuns], ask.loc[comuns]
    colunas = ["abertura", "maxima", "minima", "fechamento"]
    validas = b[colunas].notna().all(axis=1) & a[colunas].notna().all(axis=1)
    validas &= (b[colunas] > 0).all(axis=1) & (a[colunas] > 0).all(axis=1)
    validas &= a["abertura"].ge(b["abertura"]) & a["fechamento"].ge(b["fechamento"])
    return b[validas], a[validas], {"bid": len(bid), "ask": len(ask), "comuns": len(comuns),
                                   "invalidos": int((~validas).sum()), "validos": int(validas.sum())}


def simular(bid: pd.DataFrame, ask: pd.DataFrame, sinais: pd.Series, atr: pd.Series,
            regra: RegraSaida = RegraSaida(), inversao: pd.Series | None = None,
            pip: float = 0.0001) -> pd.DataFrame:
    """Compra no ASK, encerra no BID; venda no BID, encerra no ASK.

    Entrada na abertura do minuto imediatamente apos o sinal. Sem essa cotacao,
    rejeita a entrada em vez de a empurrar para depois do fim de semana.
    Stop precede alvo quando ambos cabem na vela. Gap contra o stop sai na abertura.
    O trailing so muda depois de fechar a vela e so vale na vela seguinte.
    Posicao ainda aberta no fim permanece sem resultado, nunca e encerrada artificialmente.
    """
    if pip <= 0:
        raise ValueError("Pip precisa ser positivo.")
    if not bid.index.equals(ask.index):
        raise ValueError("Use cotacoes BID/ASK previamente alinhadas.")
    index = bid.index
    nanos = index.as_unit("ns").asi8
    lado = sinais.reindex(index).fillna(0).to_numpy()
    amplitude = atr.reindex(index).to_numpy()
    virada = inversao.reindex(index).fillna(0).to_numpy() if inversao is not None else np.zeros(len(index))
    campos = ("abertura", "maxima", "minima", "fechamento")
    b, a = bid[list(campos)].to_numpy(), ask[list(campos)].to_numpy()
    saida = []
    livre = 0
    for i in np.flatnonzero(lado):
        if i < livre or i + 1 >= len(index) or not np.isfinite(amplitude[i]) or amplitude[i] <= 0:
            continue
        if lado[i] not in (-1, 1):
            raise ValueError("Sinal deve ser -1, 0 ou 1.")
        entrada_i, d = i + 1, int(lado[i])
        if nanos[entrada_i] - nanos[i] != 60_000_000_000:
            continue
        entrada = a[entrada_i, 0] if d > 0 else b[entrada_i, 0]
        stop = entrada - d * regra.stop_atr * amplitude[i]
        alvo = entrada + d * regra.alvo_atr * amplitude[i] if regra.alvo_atr is not None else None
        melhor = entrada
        encerrada, preco_saida, motivo = None, np.nan, "aberta"
        lacunas = False
        percurso = b if d > 0 else a
        for j in range(entrada_i, len(index)):
            if j > entrada_i and nanos[j] - nanos[j - 1] > 60_000_000_000:
                lacunas = True
            o, h, l, c = percurso[j]
            if (d > 0 and o <= stop) or (d < 0 and o >= stop):
                encerrada, preco_saida, motivo = j, o, "gap_stop"
            elif (d > 0 and l <= stop) or (d < 0 and h >= stop):
                encerrada, preco_saida, motivo = j, stop, "stop"
            elif alvo is not None and ((d > 0 and h >= alvo) or (d < 0 and l <= alvo)):
                encerrada, preco_saida, motivo = j, alvo, "alvo"
            elif virada[j] == -d:
                encerrada, preco_saida, motivo = j, c, "inversao"
            elif regra.minutos is not None and nanos[j] + 60_000_000_000 - nanos[entrada_i] >= regra.minutos * 60_000_000_000:
                encerrada, preco_saida, motivo = j, c, "tempo"
            if encerrada is not None:
                break
            if regra.trailing_atr is not None:
                melhor = max(melhor, c) if d > 0 else min(melhor, c)
                if d * (melhor - entrada) >= regra.ativar_trailing_atr * amplitude[i]:
                    novo = melhor - d * regra.trailing_atr * amplitude[i]
                    stop = max(stop, novo) if d > 0 else min(stop, novo)
        # A estrategia nao recebe um novo sinal no fechamento que a fez sair.
        livre = encerrada + 1 if encerrada is not None else len(index)
        saida.append({"sinal_em": index[i], "entrada_em": index[entrada_i],
                      "saida_em": index[encerrada] + pd.Timedelta(minutes=1) if encerrada is not None else pd.NaT,
                      "direcao": d, "preco_entrada": float(entrada), "preco_saida": float(preco_saida),
                      "pips_bidask": float(d * (preco_saida - entrada) / pip), "motivo": motivo,
                      "lacuna_durante": lacunas, "posicao_sinal": int(i)})
    resultado = pd.DataFrame(saida, columns=["sinal_em", "entrada_em", "saida_em", "direcao", "preco_entrada", "preco_saida",
                                            "pips_bidask", "motivo", "lacuna_durante", "posicao_sinal"])
    for coluna in ("sinal_em", "entrada_em", "saida_em"):
        resultado[coluna] = pd.to_datetime(resultado[coluna], utc=True)
    return resultado


def disponiveis_para_treino(operacoes: pd.DataFrame, antes_de: pd.Timestamp) -> pd.DataFrame:
    """O alvo so pode entrar no treino depois que a operacao encerrou; purga atravessamentos."""
    return operacoes[operacoes["saida_em"].notna() & (operacoes["saida_em"] < antes_de)]


def uma_carteira(operacoes: pd.DataFrame, score: str = "score") -> pd.DataFrame:
    """Entre candidatos simultaneos, escolhe pelo score conhecido no sinal, sem usar o P&L.

    Intervalos de ocupacao sao os da simulacao ja feita: sinais posteriores a uma
    entrada so sao considerados depois de a saida daquela posicao ter ocorrido.
    """
    if operacoes.empty:
        return operacoes.copy()
    ordem = operacoes.sort_values(["sinal_em", score, "estrategia"], ascending=[True, False, True], kind="stable")
    livre = None
    escolhidas = []
    for idx, linha in ordem.iterrows():
        if livre is not None and linha["sinal_em"] + pd.Timedelta(minutes=1) <= livre:
            continue
        escolhidas.append(idx)
        if pd.isna(linha["saida_em"]):
            break
        livre = linha["saida_em"]
    return ordem.loc[escolhidas]


def medir(operacoes: pd.DataFrame, custo_extra_pips: float = 0.5, unidades: float = 1000,
          sorteios: int = 1000, pip: float = 0.0001) -> dict:
    """P&L com spread observado mais custo extra hipotetico por ida e volta.

    O custo extra nao e uma cotacao de corretora e nao simula mudanca de preenchimentos.
    Intervalo de expectativa por bootstrap dos dias com operacoes.
    """
    if custo_extra_pips < 0 or unidades <= 0 or pip <= 0:
        raise ValueError("Custos e tamanho invalidos.")
    fechadas = operacoes[operacoes["pips_bidask"].notna()].sort_values("saida_em")
    if fechadas.empty:
        return {"operacoes": 0, "abertas": len(operacoes), "extra_pips": custo_extra_pips}
    pips = fechadas["pips_bidask"].to_numpy() - custo_extra_pips
    ganhos, perdas = pips[pips > 0].sum(), -pips[pips < 0].sum()
    saldo = np.r_[0, pips.cumsum()]
    dias = fechadas["entrada_em"].dt.floor("D")
    diario = pd.DataFrame({"dia": dias, "pips": pips, "n": 1}).groupby("dia")[["pips", "n"]].sum()
    escolhidos = np.random.default_rng(0).integers(0, len(diario), (sorteios, len(diario)))
    somas = diario.to_numpy()[escolhidos].sum(axis=1)
    expectativa = somas[:, 0] / somas[:, 1]
    p_valor = float(stats.ttest_1samp(diario["pips"], 0, alternative="greater").pvalue) if len(diario) > 1 and diario["pips"].std() > 0 else 1.0
    return {"operacoes": len(pips), "abertas": len(operacoes) - len(fechadas), "ganhos": int((pips > 0).sum()),
            "perdas": int((pips < 0).sum()), "empates": int((pips == 0).sum()), "acerto": float((pips > 0).mean()),
            "saldo_pips": float(pips.sum()), "media_pips": float(pips.mean()),
            "saldo_usd": float(pips.sum() * pip * unidades), "unidades": unidades,
            "fator_lucro": float(ganhos / perdas) if perdas else None,
            "drawdown_pips": float((np.maximum.accumulate(saldo) - saldo).max()),
            "expectativa_ic95_pips": np.quantile(expectativa, [0.025, 0.975]).tolist(),
            "dias_com_operacoes": len(diario), "p_valor_dias": p_valor,
            "duracao_mediana_min": float((fechadas["saida_em"] - fechadas["entrada_em"]).dt.total_seconds().median() / 60),
            "extra_pips": custo_extra_pips, "com_lacunas": int(fechadas["lacuna_durante"].sum())}
