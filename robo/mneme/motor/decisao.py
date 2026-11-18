"""Decision Engine: junta as técnicas com os pesos aprendidos e pergunta se a conta fecha nesta modalidade. Sem LLM e sem rede."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..laboratorio.confluencia import decidir
from .modalidades import Estrategia


@dataclass(frozen=True)
class Decisao:
    estrategia: Estrategia
    vela: pd.Timestamp
    direcao: int
    forca: float  # saída bruta do modelo: serve para comparar previsões, não é probabilidade de acerto
    operar: bool
    motivo_tecnico: str
    expectativa: float | None
    evidencia: dict
    motivos_contra: tuple[str, ...] = ()
    contexto: tuple[dict, ...] = field(default=())


def bloqueio_multitempo(direcao: int, confirmacao: dict | None, tempo: str) -> str | None:
    """A vela menor só dá entrada se o modelo da vela maior também tiver convicção.

    O valor de ``tempo`` vem da estratégia configurada; esta função não escolhe
    nem fixa um timeframe. A confirmação é técnica, não textual.
    """
    if confirmacao is None:
        return f"{tempo}: sem confluência suficiente"
    if int(confirmacao["direcao"]) != direcao:
        return f"{tempo}: direção contrária"
    return None


def decidir_operacao(estrategia: Estrategia, modelo: dict, linha: pd.Series, vela: pd.Timestamp, min_operacoes: int, contexto: tuple[dict, ...] = (),
                     bloqueios: tuple[str, ...] = ()) -> Decisao | None:
    """`None` quer dizer sem oportunidade. O contexto da LLM vai junto para o diário, mas só decide depois de provar utilidade."""
    base = decidir(modelo, linha)
    if base is None:
        return None
    evidencia = modelo.get("evidencia") or {}
    expectativa = estrategia.modalidade.expectativa(evidencia)
    contra = list(bloqueios)
    if not estrategia.modalidade.permite(base["direcao"]):
        contra.append("esta modalidade não permite vender")
    if evidencia.get("operacoes", 0) < min_operacoes:
        contra.append(f"evidência curta: {evidencia.get('operacoes', 0)} operações medidas")
    if expectativa is None or expectativa <= 0:
        contra.append("expectativa não positiva nesta modalidade" if expectativa is not None else "sem medição nesta modalidade")
    return Decisao(estrategia, vela, base["direcao"], abs(base["prob_sobe"] - 0.5), not contra, base["motivo"], expectativa, evidencia, tuple(contra), contexto)
