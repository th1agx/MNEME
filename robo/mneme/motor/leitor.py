"""O ritmo assíncrono: a LLM lê as notícias com calma e guarda o contexto com hora, validade e origem. O motor consulta sem nunca esperar uma resposta."""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx
import pandas as pd

from ..analista import ClienteLLM, leitura_da_regra, ler_noticia
from ..dados.eventos import ArmazemEventos
from ..noticias import filtrar_fontes_habilitadas
from .diario import Diario

log = logging.getLogger("mneme.motor.leitor")

VALIDADE = timedelta(hours=6)
JANELA = timedelta(hours=24)


def ler_proxima(cliente: ClienteLLM, eventos: ArmazemEventos, diario: Diario, agora: pd.Timestamp) -> bool:
    """Lê a notícia recente mais nova que ainda não foi lida. Os ativos vêm da regra, que acerta mais neles, e o sentimento da LLM, com evidência conferida no texto."""
    noticias = filtrar_fontes_habilitadas(eventos.ler("noticias", "GLOBAL"))
    if noticias.empty:
        return False
    recentes = noticias[(noticias["recebido_em"] >= agora - JANELA) & (noticias["recebido_em"] <= agora)].sort_values("recebido_em", ascending=False)
    for _, n in recentes.iterrows():
        marca = f"leitura:{n['id']}"
        if diario.contexto_lido(marca):
            continue
        suspeito = n.get("suspeito", False)
        if pd.notna(suspeito) and bool(suspeito):
            diario.gravar_contexto(marca, "__lida__", "marca", {"verificada": False, "motivo": "texto_suspeito_ignorado"},
                                  "regra:injecao", agora, agora + JANELA)
            return True
        regra = leitura_da_regra(n["titulo"], n["resumo"], n["categoria"])
        leitura = ler_noticia(cliente, n["titulo"], n["resumo"])
        origem = f"llm:{cliente.modelo}"
        criado = pd.Timestamp(n["recebido_em"])
        # A marca fica mesmo sem evidência verificada: ler de novo a mesma notícia daria o mesmo resultado.
        diario.gravar_contexto(marca, "__lida__", "marca", {"verificada": leitura.verificada, "motivo": leitura.motivo}, origem, agora, agora + JANELA)
        if leitura.verificada and leitura.relevante:
            for ativo in regra["ativos"]:
                diario.gravar_contexto(f"{marca}:{ativo}", ativo, "noticia", {"titulo": n["titulo"][:160], "tipo": leitura.tipo, "sentimento": leitura.sentimento, "evidencia": leitura.evidencia[:200]}, origem, agora, criado + VALIDADE)
        return True
    return False


def servico_leitor(cliente: ClienteLLM, eventos: ArmazemEventos, diario: Diario, relogio, parar, dormir) -> None:
    while not parar():
        try:
            if not ler_proxima(cliente, eventos, diario, pd.Timestamp(relogio())):
                dormir(60)
        except (httpx.HTTPError, OSError, ValueError) as erro:
            # Se a LLM cair, o motor não percebe: só o contexto deixa de ser renovado até vencer.
            log.warning("Leitura falhou: %s", erro)
            dormir(120)
