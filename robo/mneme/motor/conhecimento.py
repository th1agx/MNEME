"""Conhecimento e notícias chegando à decisão com rastro (E7 e E8), sem decidir por ela.

- `anexar_conhecimento`: no ritmo assíncrono (ciclo do Vault), consulta o RAG para cada estratégia do motor e grava
  os trechos mais relevantes como contexto, com origem, natureza, confiabilidade e validade. O motor só lê do SQLite.
- `efeito_do_contexto`: mede, nas decisões já apuradas, se a notícia que concordava com a direção acertou mais do que
  a que discordava ou do que a falta de notícia. É o que decide se o contexto um dia pode pesar na decisão.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pandas as pd

from ..laboratorio.validacao import intervalo_wilson
from .diario import Diario
from .modalidades import Estrategia

VALIDADE = timedelta(hours=24)
NOMES = {"BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana", "EURUSD": "euro dólar forex", "GBPUSD": "libra dólar forex",
         "USDJPY": "dólar iene forex", "XAUUSD": "ouro"}
DESCRICAO = {"expiracao_fixa": "expiração fixa CALL PUT", "com_stop": "compra e venda com stop e alvo"}


def chave_da_estrategia(e: Estrategia) -> str:
    return f"estrategia:{e.nome}"


def pergunta(e: Estrategia) -> str:
    return f"{NOMES.get(e.ativo, e.ativo)} {DESCRICAO.get(e.modalidade.tipo, e.modalidade.tipo)} {e.expiracao} minutos resultado do laboratório"


def anexar_conhecimento(diario: Diario, biblioteca, estrategias: tuple[Estrategia, ...], agora: pd.Timestamp, k: int = 3) -> int:
    """Troca o conhecimento de cada estratégia pelo da consulta de agora. Falha numa estratégia não impede as outras."""
    gravados = 0
    for e in estrategias:
        try:
            achados = biblioteca.consultar(pergunta(e), k=k)
        except Exception:
            continue
        for posicao, r in enumerate(achados):
            diario.gravar_contexto(f"conhecimento:{e.nome}:{posicao}", chave_da_estrategia(e), "conhecimento",
                                   {"titulo": r.titulo[:160], "origem": r.origem, "confiabilidade": r.confiabilidade, "suspeito": r.suspeito,
                                    "trecho": r.texto[:240], "pergunta": pergunta(e)}, "rag:biblioteca", agora, agora + VALIDADE)
            gravados += 1
    diario.con.commit()
    return gravados


def _sentimento(contexto: list[dict]) -> int:
    """Soma do sentimento das notícias vigentes na decisão: +1, -1 ou 0."""
    total = sum(int(c["valor"].get("sentimento", 0)) for c in contexto if c.get("tipo") == "noticia")
    return (total > 0) - (total < 0)


def efeito_do_contexto(diario: Diario, tipo: str | None = None) -> list[dict]:
    """Acerto por relação entre a notícia e a direção, com intervalo de 95%. Empates não contam."""
    filtro = "AND tipo = ?" if tipo else ""
    linhas = diario.con.execute(f"SELECT direcao, resultado, contexto FROM decisoes WHERE situacao = 'encerrada' AND resultado IN ('ganho', 'perda') {filtro}",
                                (tipo,) if tipo else ()).fetchall()
    grupos: dict[str, list[bool]] = {"a favor": [], "contra": [], "neutra": [], "sem notícia": []}
    for l in linhas:
        contexto = json.loads(l["contexto"])
        if not any(c.get("tipo") == "noticia" for c in contexto):
            grupo = "sem notícia"
        else:
            s = _sentimento(contexto)
            grupo = "neutra" if s == 0 else "a favor" if s == l["direcao"] else "contra"
        grupos[grupo].append(l["resultado"] == "ganho")
    saida = []
    for grupo, ganhos in grupos.items():
        n, acertos = len(ganhos), sum(ganhos)
        inferior, superior = intervalo_wilson(acertos, n) if n else (float("nan"), float("nan"))
        saida.append({"grupo": grupo, "decisoes": n, "acerto": acertos / n if n else float("nan"), "ic95": (inferior, superior)})
    return saida
