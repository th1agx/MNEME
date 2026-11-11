"""O que muda de um mercado para outro: payout e expiração, ou stop, alvo e custo. A arquitetura é uma só, e cada estratégia é medida na própria modalidade."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..digitais.liquidacao import liquidar_digital, pnl_digital
from ..digitais.modalidade import ExpiracaoFixa
from ..mercados.liquidacao import liquidar_posicao
from ..mercados.modalidade import ComStop

# Cada domínio define a própria modalidade (Motor 02: opções digitais; Motor 01: mercados). O motor é o núcleo comum.
Modalidade = ExpiracaoFixa | ComStop


@dataclass(frozen=True)
class Estrategia:
    """Candle é onde se decide e expiração é quanto a operação dura. São coisas separadas."""
    mercado: str
    ativo: str
    candle: int
    expiracao: int
    modalidade: Modalidade
    fracao: float = 0.1

    @property
    def nome(self) -> str:
        return f"{self.ativo}|{self.modalidade.tipo}|{self.candle}m|{self.expiracao}m"

    @property
    def arquivo(self) -> str:
        return self.nome.replace("|", "_") + ".json"


@dataclass(frozen=True)
class Limites:
    """Cada carteira simulada é de uma estratégia, para elas competirem medidas. Sem valor em algum campo, o Risk Engine recusa."""
    meta_dia_pct: float | None = None
    perda_dia_pct: float | None = None
    max_operacoes_dia: int | None = None
    max_simultaneas_total: int | None = None
    max_perdas_seguidas: int | None = None
    drawdown_max_pct: float | None = None
    idade_maxima_dados_min: float | None = None


@dataclass(frozen=True)
class Configuracao:
    modo: str
    banca: float
    risco_por_operacao: float
    min_operacoes_evidencia: int
    limites: Limites
    estrategias: tuple[Estrategia, ...]


def _modalidade(m: dict) -> Modalidade:
    if m["tipo"] == "expiracao_fixa":
        return ExpiracaoFixa(float(m["payout"]), bool(m.get("payout_medido", False)))
    if m["tipo"] == "com_stop":
        return ComStop(float(m["custo_bps"]), float(m["stop_atr"]), float(m["alvo_atr"]), bool(m["vende"]), bool(m.get("custo_medido", False)))
    raise ValueError(f"Modalidade desconhecida: {m['tipo']}")


def carregar_configuracao(caminho: Path | str) -> Configuracao | None:
    """Sem arquivo, o robô só observa: nenhum valor de estratégia vive no código."""
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    d = json.loads(caminho.read_text(encoding="utf-8"))
    estrategias = []
    for mercado in d["mercados"]:
        for ativo in mercado["ativos"]:
            for m in mercado["modalidades"]:
                estrategias.append(Estrategia(mercado["mercado"], ativo, int(m["candle"]), int(m["expiracao"]), _modalidade(m), float(m.get("fracao", 0.1))))
    return Configuracao(d["modo"], float(d["banca"]), float(d["risco_por_operacao"]), int(d["min_operacoes_evidencia"]), Limites(**d["limites"]), tuple(estrategias))


def _janela(v: pd.DataFrame, entrada_em: pd.Timestamp, minutos: int) -> pd.DataFrame:
    """Uma linha por minuto do prazo, a partir da entrada. Minuto faltando vira vazio, como no laboratório."""
    return v.reindex(pd.date_range(entrada_em, periods=minutos, freq="1min"))


def liquidar_fixa(v: pd.DataFrame, entrada_em: pd.Timestamp, expiracao: int, direcao: int, payout: float) -> dict | None:
    """Entra na abertura e fecha no fechamento do último minuto do prazo. Empate devolve a aposta. Sem preço nos dois pontos, não apura.

    A regra está em `mneme.liquidacao`, a mesma do laboratório.
    """
    w = _janela(v, entrada_em, expiracao)
    d = liquidar_digital(w["abertura"].to_numpy(dtype=float), w["fechamento"].to_numpy(dtype=float), 0, expiracao, direcao)
    if d is None:
        return None
    return {"resultado": d.resultado, "pnl": pnl_digital(d.resultado, payout), "preco_entrada": d.preco_entrada, "preco_saida": d.preco_saida, "encerrado_por": "expiracao"}


def liquidar_stop(v: pd.DataFrame, entrada_em: pd.Timestamp, tempo_max: int, direcao: int, distancia_stop: float, distancia_alvo: float, custo_bps: float) -> dict | None:
    """Stop, alvo e tempo a partir da entrada real, pela regra de `mneme.liquidacao` (a mesma do laboratório).

    Vela que abre além do stop sai na abertura (gap). Até 11/11/2026 o motor saía no preço do stop, o que era otimista.
    Se stop e alvo caem no mesmo minuto, vale o stop. Prazo ainda não terminado nas velas disponíveis: não apura.
    """
    w = _janela(v, entrada_em, tempo_max)
    p = liquidar_posicao(*(w[k].to_numpy(dtype=float) for k in ("abertura", "maxima", "minima", "fechamento")), 0, tempo_max, direcao,
                         distancia_stop, distancia_alvo)
    if p is None:
        return None
    custo_r = custo_bps / 1e4 * p.preco_entrada / distancia_stop
    bruto = (p.preco_saida - p.preco_entrada) * direcao / distancia_stop
    pnl = bruto - custo_r
    return {"resultado": "ganho" if pnl > 0 else "perda", "pnl": pnl, "preco_entrada": p.preco_entrada, "preco_saida": p.preco_saida,
            "encerrado_por": p.motivo, "pnl_bruto": bruto, "custo_r": custo_r}


def amplitude_media(v: pd.DataFrame, candle: int, periodo: int = 14) -> pd.Series:
    """Amplitude média dos últimos candles, medida só com velas já fechadas. É o ATR sem gap, que serve para qualquer ativo."""
    amplitude = v["maxima"].rolling(candle).max() - v["minima"].rolling(candle).min()
    grade = amplitude[(amplitude.index.hour * 60 + amplitude.index.minute + 1) % candle == 0]
    return grade.rolling(periodo).mean()
