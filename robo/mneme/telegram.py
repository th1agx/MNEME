"""Dicas no grupo do Telegram: uma por entrada e uma por saída do robô.

As dicas entram numa fila no banco e são enviadas a cada ciclo; sem token ou grupo no .env, ficam na fila.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import httpx

from .carteira import BRASILIA

IDADE_MAXIMA = timedelta(minutes=10)


def _pct(valor: float) -> str:
    texto = f"{valor:+.2f}%".replace(".", ",")
    return texto


def texto_entrada(simbolo: str, traders: int, acerto_medio: float | None, variacao_24h: float | None, quando: datetime) -> str:
    hora = quando.astimezone(BRASILIA).strftime("%H:%M")
    linha = " · ".join(filter(None, [
        f"{traders} {'trader' if traders == 1 else 'traders'} de alto acerto",
        f"acerto médio {acerto_medio:.0f}%" if acerto_medio is not None else "",
        hora,
    ]))
    if variacao_24h is None:
        variacao = "📊 24h n/d"
    else:
        variacao = f"{'📈' if variacao_24h > 0 else '📉' if variacao_24h < 0 else '📊'} {_pct(variacao_24h)} 24h"
    return "\n\n".join([f"🟢 ${simbolo} · ENTRADA", linha, variacao])


def texto_saida(simbolo: str, venderam: int, traders: int, resultado_pct: float | None, quando: datetime) -> str:
    hora = quando.astimezone(BRASILIA).strftime("%H:%M")
    resultado = ("Resultado n/d" if resultado_pct is None
                 else f"{'✅' if resultado_pct >= 0 else '❌'} Resultado da operação: {_pct(resultado_pct)}")
    return "\n\n".join([f"🔴 ${simbolo} · SAÍDA",
                        f"{venderam} de {traders} traders de alto acerto da entrada venderam · {hora}", resultado])


def enfileirar(con: sqlite3.Connection, texto: str, agora: datetime) -> None:
    con.execute("INSERT INTO dicas (texto, criada_em) VALUES (?, ?)", (texto, agora.isoformat()))


class Telegram:
    def __init__(self, token: str, grupo: str, cliente: httpx.Client | None = None):
        self.token, self.grupo = token, grupo
        self.cliente = cliente or httpx.Client(timeout=10)

    @property
    def configurado(self) -> bool:
        return bool(self.token and self.grupo)

    def enviar_pendentes(self, con: sqlite3.Connection, agora: datetime) -> int:
        """Envia a fila em ordem. Dica velha expira: avisar uma entrada com atraso é pior que não avisar."""
        con.execute("UPDATE dicas SET situacao = 'expirada' WHERE situacao = 'pendente' AND criada_em < ?",
                    ((agora - IDADE_MAXIMA).isoformat(),))
        enviadas = 0
        if self.configurado:
            for dica in con.execute("SELECT id, texto FROM dicas WHERE situacao = 'pendente' ORDER BY id").fetchall():
                con.execute("UPDATE dicas SET tentativas = tentativas + 1 WHERE id = ?", (dica["id"],))
                try:
                    resposta = self.cliente.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                                                 json={"chat_id": self.grupo, "text": dica["texto"], "disable_web_page_preview": True})
                except Exception:  # qualquer falha do Telegram: a dica fica na fila e o robô segue
                    break
                if resposta.status_code != 200:
                    break
                con.execute("UPDATE dicas SET situacao = 'enviada', enviada_em = ? WHERE id = ?", (agora.isoformat(), dica["id"]))
                enviadas += 1
        con.commit()
        return enviadas
