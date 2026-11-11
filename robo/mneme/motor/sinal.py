"""Signal Engine: transforma a decisão num sinal estruturado. Cada modalidade tem o próprio tipo, sem campos que não se aplicam a ela."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .decisao import Decisao
from .modalidades import ComStop, ExpiracaoFixa

AVISO = "Operação simulada. Resultado passado não garante resultado futuro."


def _ceil_minuto(t: pd.Timestamp) -> pd.Timestamp:
    return t.ceil("min")


@dataclass(frozen=True)
class SinalExpiracao:
    chave: str
    estrategia: str
    mercado: str
    ativo: str
    candle: int
    acao: str  # CALL ou PUT
    preco_referencia: float
    entrada_em: str
    expira_em: str
    expiracao_min: int
    payout: float
    payout_medido: bool
    empate: float
    expectativa: float | None
    motivo: str
    # O preço vem de uma fonte de referência (Binance, Dukascopy), não da corretora de opções. Enquanto não houver
    # registro na própria plataforma, todo resultado desta modalidade é aproximação.
    fidelidade: str = "aproximacao-referencia"


@dataclass(frozen=True)
class SinalComStop:
    chave: str
    estrategia: str
    mercado: str
    ativo: str
    candle: int
    acao: str  # COMPRA ou VENDA
    preco_referencia: float
    entrada_em: str
    tempo_max_min: int
    distancia_stop: float
    distancia_alvo: float
    custo_bps: float
    custo_medido: bool
    expectativa: float | None
    motivo: str


Sinal = SinalExpiracao | SinalComStop


def chave_da_decisao(d: Decisao) -> str:
    """Uma estratégia decide uma vez por vela. É o que impede operação duplicada, inclusive depois de reiniciar."""
    return f"{d.estrategia.nome}|{d.vela.isoformat()}"


def criar_sinal(d: Decisao, preco: float, amplitude: float | None, agora: pd.Timestamp) -> Sinal | None:
    """Ninguém entra antes de o sinal existir: a entrada é a primeira abertura depois da decisão. Sem amplitude medida, não há como pôr stop."""
    e = d.estrategia
    entrada = max(_ceil_minuto(agora), d.vela + pd.Timedelta(minutes=1))
    comum = {"chave": chave_da_decisao(d), "estrategia": e.nome, "mercado": e.mercado, "ativo": e.ativo, "candle": e.candle, "preco_referencia": float(preco), "entrada_em": entrada.isoformat(), "expectativa": d.expectativa, "motivo": d.motivo_tecnico}
    m = e.modalidade
    if isinstance(m, ExpiracaoFixa):
        fim = entrada + pd.Timedelta(minutes=e.expiracao)
        return SinalExpiracao(**comum, acao="CALL" if d.direcao == 1 else "PUT", expira_em=fim.isoformat(), expiracao_min=e.expiracao, payout=m.payout, payout_medido=m.payout_medido, empate=m.empate)
    if isinstance(m, ComStop):
        if amplitude is None or not amplitude > 0:
            return None
        return SinalComStop(**comum, acao="COMPRA" if d.direcao == 1 else "VENDA", tempo_max_min=e.expiracao, distancia_stop=float(amplitude * m.stop_atr), distancia_alvo=float(amplitude * m.alvo_atr), custo_bps=m.custo_bps, custo_medido=m.custo_medido)
    raise TypeError(type(m))


def como_dicionario(s: Sinal) -> dict:
    return asdict(s)


def texto_do_sinal(s: Sinal) -> str:
    """A mensagem não mostra probabilidade: o número só existiria com calibração validada, e hipótese de payout ou custo vem dita."""
    if isinstance(s, SinalExpiracao):
        payout = f"{s.payout:.0%}" + ("" if s.payout_medido else " (hipótese)")
        fidelidade = ("Fidelidade: aproximação (preço de referência, não da corretora)" if s.fidelidade == "aproximacao-referencia"
                      else f"Fidelidade: {s.fidelidade}")
        return "\n".join([f"SINAL · {s.ativo} · {s.acao}", f"Entrada: {s.entrada_em[11:16]} UTC · Expiração: {s.expiracao_min} min", f"Referência: {s.preco_referencia:g}", f"Payout: {payout} · Empate: {s.empate:.2%}", fidelidade, f"Por quê: {s.motivo}", AVISO])
    custo = f"{s.custo_bps:g} bps" + ("" if s.custo_medido else " (hipótese)")
    return "\n".join([f"SINAL · {s.ativo} · {s.acao}", f"Entrada: {s.entrada_em[11:16]} UTC · Tempo máximo: {s.tempo_max_min} min", f"Referência: {s.preco_referencia:g}", f"Stop: {s.distancia_stop:g} · Alvo: {s.distancia_alvo:g} · Custo: {custo}", f"Por quê: {s.motivo}", AVISO])
